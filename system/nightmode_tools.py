# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import re
import datetime
from typing import Optional, Dict, Any
from telethon.tl.types import ChatBannedRights
from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest
from telethon.errors import ChatAdminRequiredError, UserAdminInvalidError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

# Initialize AsyncIOScheduler
scheduler = AsyncIOScheduler()
if not scheduler.running:
    try:
        scheduler.start()
    except Exception:
        pass

# MongoDB / DB collection for nightmode persistence
nightmode_db = Friday.db.make_collection("NIGHTMODE")

# In-memory registry of scheduled jobs
_SCHEDULED_JOBS: Dict[str, Dict[str, Any]] = {}

# Rights configurations
LOCKED_RIGHTS = ChatBannedRights(
    until_date=None,
    send_messages=True,
    send_media=True,
    send_stickers=True,
    send_gifs=True,
    send_games=True,
    send_inline=True,
    embed_links=True,
    send_polls=True,
    change_info=True,
    invite_users=False,
    pin_messages=True,
)

UNLOCKED_RIGHTS = ChatBannedRights(
    until_date=None,
    send_messages=False,
    send_media=False,
    send_stickers=False,
    send_gifs=False,
    send_games=False,
    send_inline=False,
    embed_links=False,
    send_polls=False,
    change_info=False,
    invite_users=False,
    pin_messages=False,
)

MEDIA_ONLY_LOCKED = ChatBannedRights(
    until_date=None,
    send_messages=False,
    send_media=True,
    send_stickers=True,
    send_gifs=True,
    send_games=True,
    send_inline=True,
    embed_links=True,
    send_polls=True,
    change_info=True,
    invite_users=False,
    pin_messages=True,
)


async def _is_admin(c: Client, chat_id: int, user_id: int) -> bool:
    """Check if the requesting user has administrative permissions in the chat."""
    try:
        perms = await c.get_permissions(chat_id, user_id)
        return bool(perms.is_admin or perms.is_creator)
    except Exception:
        return False


async def apply_night_lock(chat_id: int, mode: str = "full", custom_msg: Optional[str] = None):
    """Callback to execute chat lockdown."""
    try:
        rights = MEDIA_ONLY_LOCKED if mode == "media" else LOCKED_RIGHTS
        await Friday.client(EditChatDefaultBannedRightsRequest(peer=chat_id, banned_rights=rights))
        announcement = custom_msg or (
            "🌙 <b>Night Mode Activated!</b>\n\n"
            "This group has been automatically muted for the quiet hours.\n"
            "Rest well, messages will be re-enabled at scheduled wake-up time! 💤"
        )
        await Friday.client.send_message(chat_id, announcement)
    except Exception as e:
        print(f"[NightMode] Error locking chat {chat_id}: {e}")


async def apply_night_unlock(chat_id: int, custom_msg: Optional[str] = None):
    """Callback to unlock chat permissions."""
    try:
        await Friday.client(EditChatDefaultBannedRightsRequest(peer=chat_id, banned_rights=UNLOCKED_RIGHTS))
        announcement = custom_msg or (
            "☀️ <b>Good Morning! Night Mode Deactivated!</b>\n\n"
            "Quiet hours have ended. Chat permissions have been restored.\n"
            "Enjoy your day and chat away! 🚀"
        )
        await Friday.client.send_message(chat_id, announcement)
    except Exception as e:
        print(f"[NightMode] Error unlocking chat {chat_id}: {e}")


def _schedule_chat_jobs(chat_id: int, start_time: str, end_time: str, tz: str = "UTC", mode: str = "full",
                        lock_msg: Optional[str] = None, unlock_msg: Optional[str] = None):
    """Register cron jobs in AsyncIOScheduler."""
    shour, smin = [int(x) for x in start_time.split(":")]
    ehour, emin = [int(x) for x in end_time.split(":")]

    lock_job_id = f"nightlock_{chat_id}"
    unlock_job_id = f"nightunlock_{chat_id}"

    # Remove existing jobs if any
    for jid in (lock_job_id, unlock_job_id):
        try:
            scheduler.remove_job(jid)
        except Exception:
            pass

    # Add new jobs
    scheduler.add_job(
        apply_night_lock,
        CronTrigger(hour=shour, minute=smin, timezone=tz),
        id=lock_job_id,
        args=[chat_id, mode, lock_msg],
        replace_existing=True,
    )
    scheduler.add_job(
        apply_night_unlock,
        CronTrigger(hour=ehour, minute=emin, timezone=tz),
        id=unlock_job_id,
        args=[chat_id, unlock_msg],
        replace_existing=True,
    )

    _SCHEDULED_JOBS[str(chat_id)] = {
        "start_time": start_time,
        "end_time": end_time,
        "timezone": tz,
        "mode": mode,
        "lock_msg": lock_msg,
        "unlock_msg": unlock_msg,
    }


@Friday.register_on_cmd(
    ["nightmode", "night"],
    cmd_help={
        "help": "Schedule automated night mode to lock group sending permissions during quiet hours with AsyncIOScheduler.",
        "example": "nightmode 23:00 07:00 -tz Asia/Kolkata -mode full\nOptions: -mode [full|media], -tz <timezone>, -msg <custom close alert>",
    },
    requires_input=True,
)
async def set_night_mode(c: Client, m: Message):
    if not m.is_group:
        return await m.handle_message("❌ Night Mode is only applicable in groups and supergroups.")

    chat_id = m.chat_id
    user_id = m.sender_id

    # Verify user is admin
    if not await _is_admin(c, chat_id, user_id):
        return await m.handle_message("🛡️ <b>Admin Permission Required:</b> Only chat administrators can configure Night Mode.")

    raw = m.user_input.strip()
    
    # Parse options
    tz = "UTC"
    mode = "full"
    custom_lock_msg = None

    if "-tz" in raw:
        parts = raw.split("-tz")
        raw = parts[0].strip()
        tz_part = parts[1].strip().split()[0]
        tz = tz_part

    if "-mode" in raw:
        parts = raw.split("-mode")
        raw = parts[0].strip()
        mode = parts[1].strip().split()[0].lower()
        if mode not in ["full", "media"]:
            mode = "full"

    if "-msg" in raw:
        parts = raw.split("-msg", 1)
        raw = parts[0].strip()
        custom_lock_msg = parts[1].strip()

    tokens = raw.split()
    if len(tokens) < 2:
        return await m.handle_message(
            "⚠️ <b>Usage:</b> <code>.nightmode &lt;start_HH:MM&gt; &lt;end_HH:MM&gt; [-tz Timezone] [-mode full|media] [-msg Alert]</code>\n"
            "<b>Example:</b> <code>.nightmode 23:00 07:30 -tz Asia/Kolkata -mode full</code>"
        )

    start_time, end_time = tokens[0], tokens[1]
    time_regex = r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
    if not re.match(time_regex, start_time) or not re.match(time_regex, end_time):
        return await m.handle_message("❌ Invalid time format. Please use 24-hour HH:MM (e.g. <code>23:00</code>, <code>07:30</code>).")

    msg = await m.handle_message("⏳ Configuring Night Mode schedule with <code>AsyncIOScheduler</code>...")

    try:
        # Schedule jobs
        _schedule_chat_jobs(chat_id, start_time, end_time, tz=tz, mode=mode, lock_msg=custom_lock_msg)

        # Persist to database
        doc = {
            "_id": str(chat_id),
            "start_time": start_time,
            "end_time": end_time,
            "timezone": tz,
            "mode": mode,
            "lock_msg": custom_lock_msg,
            "enabled": True,
            "set_by": user_id,
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }
        await nightmode_db.update_one({"_id": str(chat_id)}, {"$set": doc}, upsert=True)

        info = (
            "🌙 <b>Night Mode Scheduled Successfully!</b>\n\n"
            f"• <b>Lockdown Time:</b> <code>{start_time}</code> ({tz})\n"
            f"• <b>Reopen Time:</b> <code>{end_time}</code> ({tz})\n"
            f"• <b>Lock Mode:</b> <code>{'All Messages' if mode == 'full' else 'Media & Links Only'}</code>\n"
            f"• <b>Engine:</b> <code>AsyncIOScheduler (cron)</code>\n\n"
            "<i>Group permissions will automatically close and reopen according to schedule.</i>"
        )
        await msg.edit_msg(info)
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to set Night Mode: <code>{e}</code>")


@Friday.register_on_cmd(
    ["nightoff", "nonight"],
    cmd_help={
        "help": "Disable and remove scheduled night mode for this group.",
        "example": "nightoff",
    },
)
async def disable_night_mode(c: Client, m: Message):
    if not m.is_group:
        return await m.handle_message("❌ Night Mode is only applicable in groups.")

    chat_id = m.chat_id
    if not await _is_admin(c, chat_id, m.sender_id):
        return await m.handle_message("🛡️ Admin permission required.")

    lock_job_id = f"nightlock_{chat_id}"
    unlock_job_id = f"nightunlock_{chat_id}"

    for jid in (lock_job_id, unlock_job_id):
        try:
            scheduler.remove_job(jid)
        except Exception:
            pass

    _SCHEDULED_JOBS.pop(str(chat_id), None)
    await nightmode_db.delete_one({"_id": str(chat_id)})

    # Restore chat permissions
    try:
        await c(EditChatDefaultBannedRightsRequest(peer=chat_id, banned_rights=UNLOCKED_RIGHTS))
    except Exception:
        pass

    await m.handle_message("🔓 <b>Night Mode Disabled:</b> Automated quiet hours removed and group permissions restored.")


@Friday.register_on_cmd(
    ["nightstatus", "nightcheck"],
    cmd_help={
        "help": "Check active night mode schedule, timezone, and current group status.",
        "example": "nightstatus",
    },
)
async def check_night_status(c: Client, m: Message):
    if not m.is_group:
        return await m.handle_message("❌ Night Mode is only applicable in groups.")

    chat_id = m.chat_id
    data = await nightmode_db.find_one({"_id": str(chat_id)})
    if not data or not data.get("enabled"):
        return await m.handle_message("ℹ️ Night Mode is currently <b>Disabled</b> in this group.\nEnable via <code>.nightmode 23:00 07:00</code>.")

    lock_job = scheduler.get_job(f"nightlock_{chat_id}")
    unlock_job = scheduler.get_job(f"nightunlock_{chat_id}")

    next_lock = lock_job.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z") if lock_job and lock_job.next_run_time else "N/A"
    next_unlock = unlock_job.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z") if unlock_job and unlock_job.next_run_time else "N/A"

    report = (
        "🌙 <b>Group Night Mode Status</b>\n\n"
        f"• <b>Status:</b> 🟢 Active\n"
        f"• <b>Schedule:</b> <code>{data.get('start_time')}</code> ➔ <code>{data.get('end_time')}</code>\n"
        f"• <b>Timezone:</b> <code>{data.get('timezone', 'UTC')}</code>\n"
        f"• <b>Protection Mode:</b> <code>{data.get('mode', 'full').title()}</code>\n"
        f"• <b>Next Lockdown:</b> <code>{next_lock}</code>\n"
        f"• <b>Next Reopen:</b> <code>{next_unlock}</code>\n\n"
        "<i>Use .nightlock to force mute now, or .nightoff to deactivate.</i>"
    )
    await m.handle_message(report)


@Friday.register_on_cmd(
    ["nightlock", "lockchat"],
    cmd_help={
        "help": "Immediately lock group sending rights manually.",
        "example": "nightlock",
    },
)
async def force_night_lock(c: Client, m: Message):
    if not m.is_group:
        return await m.handle_message("❌ Groups only.")
    if not await _is_admin(c, m.chat_id, m.sender_id):
        return await m.handle_message("🛡️ Admin permission required.")

    msg = await m.handle_message("🔒 Muting chat permissions...")
    await apply_night_lock(m.chat_id, mode="full")
    await msg.edit_msg("🔒 <b>Chat Locked:</b> Messages disabled for members.")


@Friday.register_on_cmd(
    ["nightunlock", "unlockchat"],
    cmd_help={
        "help": "Immediately unlock group sending rights manually.",
        "example": "nightunlock",
    },
)
async def force_night_unlock(c: Client, m: Message):
    if not m.is_group:
        return await m.handle_message("❌ Groups only.")
    if not await _is_admin(c, m.chat_id, m.sender_id):
        return await m.handle_message("🛡️ Admin permission required.")

    msg = await m.handle_message("🔓 Restoring chat permissions...")
    await apply_night_unlock(m.chat_id)
    await msg.edit_msg("🔓 <b>Chat Unlocked:</b> Members can now send messages.")
