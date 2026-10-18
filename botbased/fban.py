# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import re
import time
import asyncio
from typing import Optional, List, Tuple, Dict, Any
from Main import Friday
from Main.core.types import FridayTelegramClient as Client, Message
from Main.plugins.userbot.channel_utils import digit_wrap
from Main.utils.suppress import suppress_error

# Database collection for federation configurations (segregated per client)
fed_db = Friday.db.make_collection("Federations")
DEFAULT_FED_BOT = "MissRose_bot"

_UUID_REGEX = re.compile(r"([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})")

# In-memory TTL cache to avoid spamming Rose when running multiple bans back-to-back
# {client_id: {"feds": [(fed_name, fed_id), ...], "time": timestamp}}
_FED_CACHE: Dict[int, Dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes TTL


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


def _parse_rose_feds(text: str) -> List[Tuple[str, str]]:
    """
    Extract (fed_name, fed_id) pairs from MissRose /myfeds response.
    Handles various Rose formatting variants cleanly.
    """
    feds: List[Tuple[str, str]] = []
    seen = set()

    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = _UUID_REGEX.search(line)
        if match:
            fed_id = match.group(1).lower()
            if fed_id in seen:
                continue
            seen.add(fed_id)

            # Extract name from the text preceding or following the UUID
            before_uuid = line[: match.start()].strip()
            name = before_uuid.lstrip("•-* \t0123456789.").rstrip("(`'\" :").strip()
            if not name:
                after_uuid = line[match.end() :].strip()
                name = after_uuid.strip(")-* '\"`:")
            if not name:
                name = f"Fed {fed_id[:8]}"

            feds.append((name, fed_id))

    return feds


async def _get_fed_bot_name(client_id: int) -> str:
    """Get the configured federation bot username (defaults to MissRose_bot)."""
    doc = await fed_db.find_one({"_id": f"feds_{client_id}"}) or {}
    return doc.get("fed_bot", DEFAULT_FED_BOT).lstrip("@")


async def _fetch_rose_feds_live(
    c: Client, bot_entity: Any, client_id: int, force: bool = False
) -> List[Tuple[str, str]]:
    """
    Automatically fetch all admin federations directly from MissRose (/myfeds).
    No manual storing required.
    """
    now = time.time()
    cached = _FED_CACHE.get(client_id)
    if not force and cached and (now - cached.get("time", 0)) < _CACHE_TTL:
        return cached.get("feds", [])

    all_parsed: List[Tuple[str, str]] = []

    try:
        async with c.conversation(bot_entity, timeout=14, exclusive=False) as conv:
            await conv.send_message("/myfeds")
            resp = await conv.get_response()
            first_text = resp.text or ""
            all_parsed.extend(_parse_rose_feds(first_text))

            # If Rose outputs across multiple messages
            for _ in range(2):
                try:
                    extra = await conv.get_response(timeout=2.0)
                    if extra and extra.text:
                        all_parsed.extend(_parse_rose_feds(extra.text))
                except (asyncio.TimeoutError, Exception):
                    break
    except Exception:
        pass

    # Deduplicate preserving order
    seen = set()
    unique_feds: List[Tuple[str, str]] = []
    for fname, fid in all_parsed:
        if fid not in seen:
            seen.add(fid)
            unique_feds.append((fname, fid))

    if unique_feds:
        _FED_CACHE[client_id] = {"feds": unique_feds, "time": now}

    return unique_feds


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


@Friday.register_on_cmd(
    ["fban", "fedban"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Automatically retrieve all federations from MissRose (/myfeds) and ban the target user in all of them.",
        "example": [
            "fban @spammer",
            "fban @spammer Scam and raiding chats",
            "fban 123456789 Malicious user",
        ],
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

    fed_bot_name = await _get_fed_bot_name(my_id)
    try:
        bot_entity = await c.get_input_entity(fed_bot_name)
    except Exception as e:
        return await msg.edit_msg(
            f"❌ <b>Bot Error:</b> Could not resolve federation bot <code>@{fed_bot_name}</code>: {e}"
        )

    start_t = time.time()

    # Step 1: Automatically fetch all federations from Rose live
    await msg.edit_msg(
        f"🔄 <b>Rose Federations:</b> Retrieving your federations live from <code>@{fed_bot_name}</code>..."
    )
    feds = await _fetch_rose_feds_live(c, bot_entity, my_id)

    # Fallback to single active federation if no feds returned by /myfeds
    if not feds:
        await msg.edit_msg(
            f"🔄 <b>Fbanning:</b> Sending ban request to <code>@{fed_bot_name}</code> in active federation..."
        )
        try:
            async with c.conversation(bot_entity, timeout=12, exclusive=False) as conv:
                await conv.send_message(f"/fban {user_id} {reason}")
                resp = await conv.get_response()
                resp_text = resp.text or ""
                status = _classify_fban_response(resp_text)
        except asyncio.TimeoutError:
            return await msg.edit_msg(
                f"⏱️ <b>Timeout:</b> <code>@{fed_bot_name}</code> did not reply within 12 seconds."
            )
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
            f"⏱️ <i>Elapsed: {elapsed}s</i>"
        )
        return await msg.edit_msg(out)

    # Step 2: Multi-federation ban across all federations retrieved from Rose
    total = len(feds)
    results = []

    for idx, (fed_name, fed_id) in enumerate(feds, 1):
        fed_label = f"<b>{fed_name}</b>"
        with suppress_error(msg="Update fban progress"):
            await msg.edit_msg(f"🔄 <b>Multi-FBanning:</b> [{idx}/{total}] Processing {fed_label}...")

        try:
            async with c.conversation(bot_entity, timeout=10, exclusive=False) as conv:
                # 1. Join / Switch active federation
                await conv.send_message(f"/joinfed {fed_id}")
                try:
                    await conv.get_response()
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.3)

                # 2. Issue fban
                await conv.send_message(f"/fban {user_id} {reason}")
                b_resp = await conv.get_response()
                b_text = b_resp.text or ""
                status = _classify_fban_response(b_text)
                results.append((fed_name, fed_id, status))
        except asyncio.TimeoutError:
            results.append((fed_name, fed_id, "⏱️ Timeout"))
        except Exception as exc:
            results.append((fed_name, fed_id, f"❌ {str(exc)[:30]}"))

        await asyncio.sleep(0.35)

    elapsed = round(time.time() - start_t, 2)
    banned_count = sum(1 for _, _, st in results if "Banned" in st and "Already" not in st)
    already_count = sum(1 for _, _, st in results if "Already" in st)

    summary_lines = []
    for i, (fname, fid, st) in enumerate(results, 1):
        summary_lines.append(f"  {i}. <b>{fname}</b>: {st}")

    out = (
        f"🛡️ <b>Multi-Federation Ban Completed</b>\n\n"
        f"• <b>Target:</b> {user_mention}\n"
        f"• <b>Reason:</b> <code>{reason}</code>\n"
        f"• <b>Federation Bot:</b> @{fed_bot_name}\n"
        f"• <b>Total Feds from Rose:</b> <code>{total}</code> (New: <b>{banned_count}</b> | Pre-banned: <b>{already_count}</b>)\n"
        f"• <b>Execution Time:</b> <code>{elapsed}s</code>\n\n"
        f"<b>Breakdown by Federation:</b>\n" + "\n".join(summary_lines)
    )
    return await msg.edit_msg(out)


@Friday.register_on_cmd(
    ["unfban", "funban", "unfedban"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Automatically retrieve all federations from MissRose (/myfeds) and unban the target user in all of them.",
        "example": [
            "unfban @user",
            "unfban @user False ban / appeal accepted",
            "unfban 123456789",
        ],
    },
)
async def unfban_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    user_id, user_mention, reason, err = await _extract_target(c, m)
    if err:
        return await msg.edit_msg(f"⚠️ <b>Target Error:</b> {err}")

    fed_bot_name = await _get_fed_bot_name(my_id)
    try:
        bot_entity = await c.get_input_entity(fed_bot_name)
    except Exception as e:
        return await msg.edit_msg(
            f"❌ <b>Bot Error:</b> Could not resolve federation bot <code>@{fed_bot_name}</code>: {e}"
        )

    start_t = time.time()

    # Step 1: Retrieve federations from Rose live
    await msg.edit_msg(
        f"🔄 <b>Rose Federations:</b> Retrieving your federations live from <code>@{fed_bot_name}</code>..."
    )
    feds = await _fetch_rose_feds_live(c, bot_entity, my_id)

    # Fallback to single active fed if no feds returned
    if not feds:
        await msg.edit_msg(
            f"🔄 <b>Unfbanning:</b> Sending unban request to <code>@{fed_bot_name}</code> in active federation..."
        )
        try:
            async with c.conversation(bot_entity, timeout=12, exclusive=False) as conv:
                await conv.send_message(f"/unfban {user_id} {reason}".strip())
                resp = await conv.get_response()
                resp_text = resp.text or ""
                status = _classify_unfban_response(resp_text)
        except asyncio.TimeoutError:
            return await msg.edit_msg(
                f"⏱️ <b>Timeout:</b> <code>@{fed_bot_name}</code> did not reply within 12 seconds."
            )
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

    # Step 2: Unban across all federations
    total = len(feds)
    results = []

    for idx, (fed_name, fed_id) in enumerate(feds, 1):
        fed_label = f"<b>{fed_name}</b>"
        with suppress_error(msg="Update unfban progress"):
            await msg.edit_msg(f"🔄 <b>Multi-Unfbanning:</b> [{idx}/{total}] Processing {fed_label}...")

        try:
            async with c.conversation(bot_entity, timeout=10, exclusive=False) as conv:
                await conv.send_message(f"/joinfed {fed_id}")
                try:
                    await conv.get_response()
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.3)

                await conv.send_message(f"/unfban {user_id} {reason}".strip())
                b_resp = await conv.get_response()
                b_text = b_resp.text or ""
                status = _classify_unfban_response(b_text)
                results.append((fed_name, fed_id, status))
        except asyncio.TimeoutError:
            results.append((fed_name, fed_id, "⏱️ Timeout"))
        except Exception as exc:
            results.append((fed_name, fed_id, f"❌ {str(exc)[:30]}"))

        await asyncio.sleep(0.35)

    elapsed = round(time.time() - start_t, 2)
    summary_lines = []
    for i, (fname, fid, st) in enumerate(results, 1):
        summary_lines.append(f"  {i}. <b>{fname}</b>: {st}")

    out = (
        f"🔓 <b>Multi-Federation Unban Completed</b>\n\n"
        f"• <b>Target:</b> {user_mention}\n"
        f"• <b>Reason:</b> <code>{reason}</code>\n"
        f"• <b>Federation Bot:</b> @{fed_bot_name}\n"
        f"• <b>Total Feds from Rose:</b> <code>{total}</code>\n"
        f"• <b>Execution Time:</b> <code>{elapsed}s</code>\n\n"
        f"<b>Breakdown by Federation:</b>\n" + "\n".join(summary_lines)
    )
    return await msg.edit_msg(out)


@Friday.register_on_cmd(
    ["feds", "myfeds", "getfeds", "syncfeds", "flist", "fedlist"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Retrieve and display all federations where you are an admin directly from MissRose bot (/myfeds).",
        "example": [
            "feds",
            "myfeds",
            "getfeds",
        ],
    },
)
async def feds_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    fed_bot_name = await _get_fed_bot_name(my_id)
    try:
        bot_entity = await c.get_input_entity(fed_bot_name)
    except Exception as e:
        return await msg.edit_msg(
            f"❌ <b>Bot Error:</b> Could not resolve federation bot <code>@{fed_bot_name}</code>: {e}"
        )

    await msg.edit_msg(
        f"🔄 <b>Fetching Federations:</b> Querying <code>/myfeds</code> from <code>@{fed_bot_name}</code>..."
    )
    feds = await _fetch_rose_feds_live(c, bot_entity, my_id, force=True)

    if not feds:
        return await msg.edit_msg(
            f"ℹ️ <b>No Federations Found:</b> <code>@{fed_bot_name}</code> did not list any federations where you are an admin.\n\n"
            f"<i>Make sure you have started <code>@{fed_bot_name}</code> in PM and have created or joined a federation.</i>"
        )

    lines = [f"  {i}. <b>{fname}</b>\n     └ <code>{fid}</code>" for i, (fname, fid) in enumerate(feds, 1)]

    out = (
        f"🛡️ <b>Your Rose Federations ({len(feds)} total)</b>\n"
        f"• <b>Federation Bot:</b> <code>@{fed_bot_name}</code>\n\n"
        + "\n".join(lines)
        + f"\n\n⚡ <i>Running <code>{Friday.user_command_handler}fban &lt;user&gt; [reason]</code> will automatically ban in all these {len(feds)} federations!</i>"
    )
    return await msg.edit_msg(out)


@Friday.register_on_cmd(
    ["setfedbot", "fedbot"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Set custom administration bot to converse with (defaults to MissRose_bot).",
        "example": [
            "setfedbot MissRose_bot",
            "setfedbot Rose",
        ],
    },
)
async def setfedbot_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id
    new_bot = (m.user_input or "").strip().lstrip("@")

    if not new_bot:
        curr_bot = await _get_fed_bot_name(my_id)
        return await msg.edit_msg(
            f"🤖 <b>Current Federation Bot:</b> <code>@{curr_bot}</code>\n\n"
            f"<i>To change:</i> <code>{Friday.user_command_handler}setfedbot &lt;@bot_username&gt;</code>"
        )

    await fed_db.update_one(
        {"_id": f"feds_{my_id}"},
        {"$set": {"client_id": my_id, "fed_bot": new_bot}},
        upsert=True,
    )
    # Clear memory cache on bot change
    _FED_CACHE.pop(my_id, None)
    return await msg.edit_msg(f"✅ <b>Federation Bot Updated:</b> <code>@{new_bot}</code>")


@Friday.register_on_cmd(
    ["finfo", "fcheck", "fedinfo", "fstat"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Check a user's fedban status or active federation info from MissRose.",
        "example": [
            "finfo",
            "finfo @user",
            "finfo 123456789",
            "fstat @user",
        ],
    },
)
async def finfo_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    my_id = c.myself.id

    fed_bot_name = await _get_fed_bot_name(my_id)
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
