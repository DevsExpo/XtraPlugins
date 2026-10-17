# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import re
import time
import asyncio
from typing import Optional, List, Tuple, Any
from Main import Friday
from Main.core.types import FridayTelegramClient as Client, Message
from Main.plugins.userbot.channel_utils import digit_wrap
from Main.utils.suppress import suppress_error

# Database collection for federation configurations (segregated per client)
fed_db = Friday.db.make_collection("Federations")
DEFAULT_FED_BOT = "MissRose_bot"


def _classify_fban_response(text: str) -> str:
    """Classify MissRose / Fed Bot response into clean visual badge."""
    tl = (text or "").lower()
    if any(k in tl for k in ["new fedban", "fedbanned", "banned in fed", "starting a federation ban"]):
        return "✅ Banned"
    if "already banned" in tl:
        return "⚠️ Already Banned"
    if "isn't banned" in tl or "not banned" in tl:
        return "⚠️ Not Banned"
    if "you aren't a federation admin" in tl or "not a federation admin" in tl or "not an admin" in tl:
        return "❌ Not Fed Admin"
    if "is an admin" in tl or "is a federation admin" in tl or "cannot be banned" in tl:
        return "⛔ Target is Fed Admin"
    if "invalid" in tl or "not valid" in tl:
        return "❌ Invalid Fed / Target"
    first_line = (text or "").split("\n")[0].strip()
    return f"ℹ️ {first_line[:35]}" if first_line else "✅ Sent"


def _classify_unfban_response(text: str) -> str:
    """Classify MissRose / Fed Bot unban response."""
    tl = (text or "").lower()
    if any(k in tl for k in ["unbanned", "new unfban", "fedunbanned", "removed from the fedban", "unban"]):
        if "isn't banned" in tl or "not banned" in tl:
            return "⚠️ Not Banned"
        return "✅ Unbanned"
    if "isn't banned" in tl or "not banned" in tl:
        return "⚠️ Not Banned"
    if "you aren't a federation admin" in tl or "not a federation admin" in tl or "not an admin" in tl:
        return "❌ Not Fed Admin"
    if "invalid" in tl or "not valid" in tl:
        return "❌ Invalid Fed / Target"
    first_line = (text or "").split("\n")[0].strip()
    return f"ℹ️ {first_line[:35]}" if first_line else "✅ Sent"


async def _get_fed_config(client_id: int) -> Tuple[str, List[str]]:
    """Retrieve federation configuration for the specific client."""
    doc = await fed_db.find_one({"_id": f"feds_{client_id}"}) or {}
    fed_bot = doc.get("fed_bot", DEFAULT_FED_BOT).lstrip("@")
    federations = doc.get("federations", [])
    return fed_bot, federations


async def _extract_target(c: Client, m: Message) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    """Resolve target user ID, mention, reason, and error message."""
    user_ids, reason, is_chnnl = m.get_user
    if is_chnnl:
        return None, None, None, "Channels cannot be federation banned."
    if not user_ids:
        return None, None, None, "Please reply to a target user or provide a username / ID."

    user_id = None
    user_mention = ""

    if isinstance(digit_wrap(user_ids), int):
        user_id = int(user_ids)
        user_mention = f"<a href='tg://user?id={user_id}'>User</a> (<code>{user_id}</code>)"
    else:
        try:
            user_obj = await c.get_users(user_ids)
            user_id = user_obj.id
            name = getattr(user_obj, "first_name", "User") or "User"
            uname = f"@{user_obj.username}" if getattr(user_obj, "username", None) else f"<code>{user_id}</code>"
            user_mention = f"<a href='tg://user?id={user_id}'>{name}</a> ({uname})"
        except Exception as e:
            return None, None, None, f"Could not resolve target <code>{user_ids}</code>: {str(e)[:60]}"

    return user_id, user_mention, reason or "Federation Ban via Friday", None


# ==========================================
# 1. Multi-Federation Ban (.fban)
# ==========================================

@Friday.register_on_cmd(
    ["fban", "fedban"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Ban a user across all configured federations (or active fed) via MissRose bot conversation.",
        "example": "fban @spammer Scam and abuse",
    },
)
async def fban_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    user_id, user_mention, reason, err = await _extract_target(c, m)
    if err:
        return await msg.edit_msg(f"⚠️ <b>Target Error:</b> {err}")
    if user_id == my_id:
        return await msg.edit_msg("❌ <b>Self Ban Prohibited:</b> You cannot fedban yourself!")

    fed_bot_name, federations = await _get_fed_config(my_id)
    try:
        bot_entity = await c.get_input_entity(fed_bot_name)
    except Exception as e:
        return await msg.edit_msg(f"❌ <b>Bot Error:</b> Could not resolve federation bot <code>@{fed_bot_name}</code>: {e}")

    start_t = time.time()

    # Case A: No custom federations saved -> Execute directly in current active fed
    if not federations:
        await msg.edit_msg(f"🔄 <b>Fbanning:</b> Sending ban request to <code>@{fed_bot_name}</code> in active federation...")
        try:
            async with c.conversation(bot_entity, timeout=12, exclusive=False) as conv:
                await conv.send_message(f"/fban {user_id} {reason}")
                resp = await conv.get_response()
                resp_text = resp.text or ""
                status = _classify_fban_response(resp_text)
        except asyncio.TimeoutError:
            return await msg.edit_msg(f"⏱️ <b>Timeout:</b> <code>@{fed_bot_name}</code> did not reply within 12 seconds.")
        except Exception as e:
            return await msg.edit_msg(f"❌ <b>Error:</b> {e}")

        elapsed = round(time.time() - start_t, 2)
        out = (
            f"🛡️ <b>Federation Ban Executed</b>\n\n"
            f"• <b>Target:</b> {user_mention}\n"
            f"• <b>Reason:</b> <code>{reason}</code>\n"
            f"• <b>Federation Bot:</b> @{fed_bot_name}\n"
            f"• <b>Status:</b> {status}\n\n"
            f"<b>Rose Response:</b>\n"
            f"<blockquote>{resp_text[:350]}</blockquote>\n\n"
            f"⏱️ <i>Elapsed: {elapsed}s</i>\n"
            f"💡 <i>Tip: Add multiple federations with <code>{Friday.user_command_handler}fadd &lt;fed_id&gt;</code> to ban across all in 1-click!</i>"
        )
        return await msg.edit_msg(out)

    # Case B: Multi-federation mode
    total = len(federations)
    results = []

    for idx, fed_id in enumerate(federations, 1):
        fed_label = f"{fed_id[:8]}...{fed_id[-4:]}" if len(fed_id) > 14 else fed_id
        with suppress_error(msg="Update fban progress"):
            await msg.edit_msg(f"🔄 <b>Multi-FBanning:</b> [{idx}/{total}] Processing <code>{fed_label}</code>...")

        try:
            async with c.conversation(bot_entity, timeout=10, exclusive=False) as conv:
                # 1. Join / Switch active federation
                await conv.send_message(f"/joinfed {fed_id}")
                try:
                    await conv.get_response()
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.4)

                # 2. Issue fban
                await conv.send_message(f"/fban {user_id} {reason}")
                b_resp = await conv.get_response()
                b_text = b_resp.text or ""
                status = _classify_fban_response(b_text)
                results.append((fed_id, status))
        except asyncio.TimeoutError:
            results.append((fed_id, "⏱️ Timeout"))
        except Exception as exc:
            results.append((fed_id, f"❌ {str(exc)[:30]}"))

        await asyncio.sleep(0.5)

    elapsed = round(time.time() - start_t, 2)
    banned_count = sum(1 for _, st in results if "Banned" in st and "Already" not in st)
    already_count = sum(1 for _, st in results if "Already" in st)

    summary_lines = []
    for i, (fid, st) in enumerate(results, 1):
        f_short = f"{fid[:8]}...{fid[-4:]}" if len(fid) > 14 else fid
        summary_lines.append(f"  {i}. <code>{f_short}</code>: {st}")

    out = (
        f"🛡️ <b>Multi-Federation Ban Completed</b>\n\n"
        f"• <b>Target:</b> {user_mention}\n"
        f"• <b>Reason:</b> <code>{reason}</code>\n"
        f"• <b>Federation Bot:</b> @{fed_bot_name}\n"
        f"• <b>Total Federations:</b> <code>{total}</code> (New: <b>{banned_count}</b> | Pre-banned: <b>{already_count}</b>)\n"
        f"• <b>Execution Time:</b> <code>{elapsed}s</code>\n\n"
        f"<b>Breakdown by Federation:</b>\n" + "\n".join(summary_lines)
    )
    return await msg.edit_msg(out)


# ==========================================
# 2. Multi-Federation Unban (.unfban / .funban)
# ==========================================

@Friday.register_on_cmd(
    ["unfban", "funban", "unfedban"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Unban a user across all configured federations (or active fed) via MissRose bot conversation.",
        "example": "unfban @user Appeal accepted",
    },
)
async def unfban_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    user_id, user_mention, reason, err = await _extract_target(c, m)
    if err:
        return await msg.edit_msg(f"⚠️ <b>Target Error:</b> {err}")

    fed_bot_name, federations = await _get_fed_config(my_id)
    try:
        bot_entity = await c.get_input_entity(fed_bot_name)
    except Exception as e:
        return await msg.edit_msg(f"❌ <b>Bot Error:</b> Could not resolve federation bot <code>@{fed_bot_name}</code>: {e}")

    start_t = time.time()

    # Case A: Single / active fed
    if not federations:
        await msg.edit_msg(f"🔄 <b>Unfbanning:</b> Sending unban request to <code>@{fed_bot_name}</code> in active federation...")
        try:
            async with c.conversation(bot_entity, timeout=12, exclusive=False) as conv:
                await conv.send_message(f"/unfban {user_id} {reason}".strip())
                resp = await conv.get_response()
                resp_text = resp.text or ""
                status = _classify_unfban_response(resp_text)
        except asyncio.TimeoutError:
            return await msg.edit_msg(f"⏱️ <b>Timeout:</b> <code>@{fed_bot_name}</code> did not reply within 12 seconds.")
        except Exception as e:
            return await msg.edit_msg(f"❌ <b>Error:</b> {e}")

        elapsed = round(time.time() - start_t, 2)
        out = (
            f"🔓 <b>Federation Unban Executed</b>\n\n"
            f"• <b>Target:</b> {user_mention}\n"
            f"• <b>Reason:</b> <code>{reason}</code>\n"
            f"• <b>Federation Bot:</b> @{fed_bot_name}\n"
            f"• <b>Status:</b> {status}\n\n"
            f"<b>Rose Response:</b>\n"
            f"<blockquote>{resp_text[:350]}</blockquote>\n\n"
            f"⏱️ <i>Elapsed: {elapsed}s</i>"
        )
        return await msg.edit_msg(out)

    # Case B: Multi-federation unban
    total = len(federations)
    results = []

    for idx, fed_id in enumerate(federations, 1):
        fed_label = f"{fed_id[:8]}...{fed_id[-4:]}" if len(fed_id) > 14 else fed_id
        with suppress_error(msg="Update unfban progress"):
            await msg.edit_msg(f"🔄 <b>Multi-Unfbanning:</b> [{idx}/{total}] Processing <code>{fed_label}</code>...")

        try:
            async with c.conversation(bot_entity, timeout=10, exclusive=False) as conv:
                await conv.send_message(f"/joinfed {fed_id}")
                try:
                    await conv.get_response()
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.4)

                await conv.send_message(f"/unfban {user_id} {reason}".strip())
                b_resp = await conv.get_response()
                b_text = b_resp.text or ""
                status = _classify_unfban_response(b_text)
                results.append((fed_id, status))
        except asyncio.TimeoutError:
            results.append((fed_id, "⏱️ Timeout"))
        except Exception as exc:
            results.append((fed_id, f"❌ {str(exc)[:30]}"))

        await asyncio.sleep(0.5)

    elapsed = round(time.time() - start_t, 2)
    summary_lines = []
    for i, (fid, st) in enumerate(results, 1):
        f_short = f"{fid[:8]}...{fid[-4:]}" if len(fid) > 14 else fid
        summary_lines.append(f"  {i}. <code>{f_short}</code>: {st}")

    out = (
        f"🔓 <b>Multi-Federation Unban Completed</b>\n\n"
        f"• <b>Target:</b> {user_mention}\n"
        f"• <b>Reason:</b> <code>{reason}</code>\n"
        f"• <b>Federation Bot:</b> @{fed_bot_name}\n"
        f"• <b>Total Federations:</b> <code>{total}</code>\n"
        f"• <b>Execution Time:</b> <code>{elapsed}s</code>\n\n"
        f"<b>Breakdown by Federation:</b>\n" + "\n".join(summary_lines)
    )
    return await msg.edit_msg(out)


# ==========================================
# 3. Add Federation ID (.fadd / .addfed)
# ==========================================

@Friday.register_on_cmd(
    ["fadd", "addfed"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Add a federation ID / UUID to your multi-fban list.",
        "example": "fadd b024220b-93ff-411a-be19-7557152ae4a1",
    },
)
async def fadd_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id
    fed_id = (m.user_input or "").strip()

    if not fed_id:
        return await msg.edit_msg(
            "⚠️ <b>Federation ID Required:</b>\n"
            f"Usage: <code>{Friday.user_command_handler}fadd &lt;federation_uuid&gt;</code>\n"
            "<i>(Get your federation ID in Rose via <code>/fedinfo</code>)</i>"
        )

    doc = await fed_db.find_one({"_id": f"feds_{my_id}"}) or {}
    current_feds = doc.get("federations", [])

    if fed_id in current_feds:
        return await msg.edit_msg(f"⚠️ Federation <code>{fed_id}</code> is already in your registered list!")

    current_feds.append(fed_id)
    await fed_db.update_one(
        {"_id": f"feds_{my_id}"},
        {"$set": {"client_id": my_id, "federations": current_feds}},
        upsert=True,
    )

    return await msg.edit_msg(
        f"✅ <b>Federation Added!</b>\n\n"
        f"• <b>ID:</b> <code>{fed_id}</code>\n"
        f"• <b>Total Registered:</b> <code>{len(current_feds)}</code> federations\n\n"
        f"<i>Run <code>{Friday.user_command_handler}flist</code> to view all registered federations.</i>"
    )


# ==========================================
# 4. Remove Federation ID (.frem / .delfed)
# ==========================================

@Friday.register_on_cmd(
    ["frem", "delfed", "rmfed"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Remove a federation ID from your multi-fban list.",
        "example": "frem b024220b-93ff-411a-be19-7557152ae4a1",
    },
)
async def frem_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id
    fed_id = (m.user_input or "").strip()

    if not fed_id:
        return await msg.edit_msg(f"⚠️ Usage: <code>{Friday.user_command_handler}frem &lt;federation_uuid&gt;</code>")

    doc = await fed_db.find_one({"_id": f"feds_{my_id}"}) or {}
    current_feds = doc.get("federations", [])

    if fed_id not in current_feds:
        return await msg.edit_msg(f"⚠️ Federation <code>{fed_id}</code> is not in your registered list.")

    current_feds.remove(fed_id)
    await fed_db.update_one(
        {"_id": f"feds_{my_id}"},
        {"$set": {"client_id": my_id, "federations": current_feds}},
        upsert=True,
    )

    return await msg.edit_msg(
        f"🗑️ <b>Federation Removed!</b>\n\n"
        f"• <b>ID:</b> <code>{fed_id}</code>\n"
        f"• <b>Remaining:</b> <code>{len(current_feds)}</code> federations"
    )


# ==========================================
# 5. List Federations (.flist / .feds)
# ==========================================

@Friday.register_on_cmd(
    ["flist", "feds", "fedlist"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "List all federations configured for multi-federation bans.",
        "example": "flist",
    },
)
async def flist_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    fed_bot_name, federations = await _get_fed_config(my_id)
    if not federations:
        return await msg.edit_msg(
            "📋 <b>No Federations Registered</b>\n\n"
            f"Target Federation Bot: <code>@{fed_bot_name}</code>\n"
            f"Add federations using: <code>{Friday.user_command_handler}fadd &lt;federation_uuid&gt;</code>\n"
            "<i>(Without saved federations, .fban acts on your currently active Rose federation)</i>"
        )

    lines = [f"  {i}. <code>{fid}</code>" for i, fid in enumerate(federations, 1)]
    out = (
        f"📋 <b>Registered Federations ({len(federations)} total):</b>\n"
        f"• <b>Bot:</b> <code>@{fed_bot_name}</code>\n\n"
        + "\n".join(lines)
        + f"\n\n💡 <i>Executing <code>{Friday.user_command_handler}fban</code> will automatically ban across all these federations.</i>"
    )
    return await msg.edit_msg(out)


# ==========================================
# 6. Clear Federations (.fclear)
# ==========================================

@Friday.register_on_cmd(
    ["fclear", "clearfeds"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Clear all registered federations from your multi-fban list.",
        "example": "fclear",
    },
)
async def fclear_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id
    await fed_db.update_one({"_id": f"feds_{my_id}"}, {"$set": {"federations": []}}, upsert=True)
    return await msg.edit_msg("🧹 <b>Cleared:</b> All registered federations have been removed.")


# ==========================================
# 7. Set Federation Bot (.setfedbot)
# ==========================================

@Friday.register_on_cmd(
    ["setfedbot", "fedbot"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Set custom administration bot to converse with (defaults to MissRose_bot).",
        "example": "setfedbot MissRose_bot",
    },
)
async def setfedbot_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id
    new_bot = (m.user_input or "").strip().lstrip("@")

    if not new_bot:
        curr_bot, _ = await _get_fed_config(my_id)
        return await msg.edit_msg(
            f"🤖 <b>Current Federation Bot:</b> <code>@{curr_bot}</code>\n\n"
            f"<i>To change:</i> <code>{Friday.user_command_handler}setfedbot &lt;@bot_username&gt;</code>"
        )

    await fed_db.update_one(
        {"_id": f"feds_{my_id}"},
        {"$set": {"client_id": my_id, "fed_bot": new_bot}},
        upsert=True,
    )
    return await msg.edit_msg(f"✅ <b>Federation Bot Updated:</b> <code>@{new_bot}</code>")


# ==========================================
# 8. Check Fedban Status / Info (.finfo / .fcheck)
# ==========================================

@Friday.register_on_cmd(
    ["finfo", "fcheck", "fedinfo", "fstat"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Check a user's fedban status or active federation info from MissRose.",
        "example": "finfo @user",
    },
)
async def finfo_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    fed_bot_name, _ = await _get_fed_config(my_id)
    try:
        bot_entity = await c.get_input_entity(fed_bot_name)
    except Exception as e:
        return await msg.edit_msg(f"❌ Could not resolve federation bot <code>@{fed_bot_name}</code>: {e}")

    user_ids, _, is_chnnl = m.get_user
    cmd_to_send = "/fedinfo"
    target_desc = "Active Federation Info"

    if user_ids and not is_chnnl:
        target_desc = f"User <code>{user_ids}</code>"
        cmd_to_send = f"/fcheck {user_ids}"

    await msg.edit_msg(f"🔍 Checking with <code>@{fed_bot_name}</code>...")
    try:
        async with c.conversation(bot_entity, timeout=12, exclusive=False) as conv:
            await conv.send_message(cmd_to_send)
            resp = await conv.get_response()
            resp_text = resp.text or "No response from bot."
    except asyncio.TimeoutError:
        return await msg.edit_msg(f"⏱️ <b>Timeout:</b> <code>@{fed_bot_name}</code> did not respond in time.")
    except Exception as e:
        return await msg.edit_msg(f"❌ <b>Error:</b> {e}")

    out = (
        f"ℹ️ <b>Federation Check ({target_desc}):</b>\n\n"
        f"<b>Response from @{fed_bot_name}:</b>\n"
        f"<blockquote>{resp_text[:500]}</blockquote>"
    )
    return await msg.edit_msg(out)
