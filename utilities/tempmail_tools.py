# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import random
import string
from typing import Optional, Dict, Any, List
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _get_tempmail_col():
    return Friday.db.make_collection("TEMP_MAILS")


@Friday.register_on_cmd(
    ["tempmail", "genmail", "disposable"],
    cmd_help={
        "help": "Generate a functional temporary disposable email address with live inbox support.",
        "example": "tempmail",
    },
)
async def generate_temp_mail(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    msg = await m.handle_message("📬 Generating fresh temporary email inbox...")
    col = _get_tempmail_col()
    user_id = m.sender_id or (getattr(c, "me", None) and c.me.id) or 0

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            domains_res = await client.get("https://api.mail.tm/domains")
            if domains_res.status_code != 200:
                return await msg.edit_msg("❌ Failed to reach mail domain registry.")

            domain_list = domains_res.json().get("hydra:member", [])
            if not domain_list:
                return await msg.edit_msg("❌ No active mail domains available.")

            domain = domain_list[0]["domain"]
            username = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
            address = f"{username}@{domain}"
            password = "".join(random.choices(string.ascii_letters + string.digits, k=14))

            # Register mailbox
            create_res = await client.post(
                "https://api.mail.tm/accounts",
                json={"address": address, "password": password},
            )
            if create_res.status_code not in (200, 201):
                return await msg.edit_msg("❌ Failed to create disposable mailbox.")

            # Get authorization token
            token_res = await client.post(
                "https://api.mail.tm/token",
                json={"address": address, "password": password},
            )
            if token_res.status_code != 200:
                return await msg.edit_msg("❌ Failed to authenticate with mail service.")

            token = token_res.json().get("token")

        # Save to database
        await col.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "address": address, "token": token}},
            upsert=True,
        )

        report = (
            "📬 <b>Disposable Email Created:</b>\n\n"
            f"<code>{address}</code>\n\n"
            f"<i>• Tap above to copy email address.</i>\n"
            f"<i>• Use <code>.checkmail</code> to view incoming messages & OTP codes.</i>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Tempmail error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["checkmail", "inbox"],
    cmd_help={
        "help": "Check incoming messages and verification OTPs for your active temporary email address.",
        "example": "checkmail or checkmail -basic",
        "user_args": [
            {
                "arg": "basic",
                "help": "Force text output without inline interactive widget.",
                "requires_input": False,
            }
        ],
    },
)
async def check_temp_mail(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    col = _get_tempmail_col()
    user_id = m.sender_id or (getattr(c, "me", None) and c.me.id) or 0
    doc = await col.find_one({"user_id": user_id})

    if not doc or not doc.get("token"):
        return await m.handle_message("❌ You have no active temporary mailbox. Generate one with <code>.tempmail</code> first.")

    address = doc.get("address")
    token = doc.get("token")

    if "-basic" not in m.user_args and "-text" not in m.user_args:
        try:
            from Main.utils.inline_helper import send_inline_widget
            if await send_inline_widget(c, m, f"tempmail:{user_id}"):
                return
        except Exception:
            pass

    msg = await m.handle_message(f"📬 Checking inbox for <code>{address}</code>...")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get("https://api.mail.tm/messages", headers=headers)

        if res.status_code == 401:
            return await msg.edit_msg("⚠️ Mail session expired. Generate a new email using <code>.tempmail</code>.")
        if res.status_code != 200:
            return await msg.edit_msg(f"❌ Mail server error: HTTP {res.status_code}")

        messages = res.json().get("hydra:member", [])
        if not messages:
            return await msg.edit_msg(
                f"📭 <b>Inbox Empty</b> for <code>{address}</code>\n"
                f"<i>No new messages received yet. Send your verification code and retry with <code>.checkmail</code>.</i>"
            )

        entries = []
        for em in messages[:5]:
            subject = em.get("subject", "No Subject")
            sender = em.get("from", {}).get("address", "Unknown Sender")
            intro = em.get("intro", "")
            date_str = em.get("createdAt", "")[:19].replace("T", " ")
            entries.append(
                f"📨 <b>From:</b> <code>{sender}</code>\n"
                f"<b>• Subject:</b> {subject}\n"
                f"<b>• Date:</b> {date_str}\n"
                f"<b>• Preview:</b> <i>{intro[:200]}</i>"
            )

        report = (
            f"📬 <b>Inbox for:</b> <code>{address}</code>\n\n"
            + "\n\n────────────────\n\n".join(entries)
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Inbox error: <code>{e}</code>")


# ==========================================
# Interactive Inline TempMail Handlers
# ==========================================

if getattr(Friday, "bot", None):
    import re
    from telethon import custom
    from Main.utils.custom_filters import filters
    from Main.utils.inline_helper import is_owner

    async def _render_tempmail_inbox(user_id: int):
        col = _get_tempmail_col()
        doc = await col.find_one({"user_id": user_id})
        if not doc or not doc.get("token"):
            text = (
                "📬 <b>Temporary Disposable Mailbox</b>\n\n"
                "<i>No active mailbox found. Generate one with:</i>\n"
                "<code>.tempmail</code>"
            )
            buttons = [[custom.Button.inline("✖ Close", f"tmail_cls:{user_id}".encode("utf-8"))]]
            return text, buttons

        address = doc.get("address", "Unknown")
        token = doc.get("token")
        headers = {"Authorization": f"Bearer {token}"}
        entries = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get("https://api.mail.tm/messages", headers=headers)
                if res.status_code == 200:
                    messages = res.json().get("hydra:member", [])
                    for em in messages[:4]:
                        sender = em.get("from", {}).get("address", "Unknown")
                        subj = em.get("subject", "No Subject")
                        entries.append(f"📨 <b>From:</b> <code>{sender}</code>\n<b>Subject:</b> {subj}")
        except Exception:
            pass

        if not entries:
            body = "📭 <i>Inbox is empty (no incoming OTPs yet).</i>"
        else:
            body = "\n\n".join(entries)

        text = (
            f"📬 <b>Active Disposable Inbox:</b>\n"
            f"<code>{address}</code>\n\n"
            f"{body}\n\n"
            f"<i>• Tap address to copy. Tap Refresh to check for incoming codes.</i>"
        )
        buttons = [
            [
                custom.Button.inline("🔄 Refresh Inbox", f"tmail_ref:{user_id}".encode("utf-8")),
                custom.Button.inline("🗑 Delete", f"tmail_del:{user_id}".encode("utf-8")),
            ],
            [custom.Button.inline("✖ Close", f"tmail_cls:{user_id}".encode("utf-8"))],
        ]
        return text, buttons

    @Friday.bot.on_inline_query(filters.regex(r"^tempmail:(\d+)"))
    async def tempmail_inline_query_handler(c, iq):
        m = re.match(r"^tempmail:(\d+)", iq.text)
        user_id = int(m.group(1)) if m else iq.sender_id
        text, buttons = await _render_tempmail_inbox(user_id)
        builder = iq.builder
        res = builder.article(
            title="📬 Disposable Email Inbox",
            description="View incoming verification emails & OTPs with live refresh button.",
            text=text,
            buttons=buttons,
            parse_mode="html",
        )
        await iq.answer([res], cache_time=0)

    @Friday.bot.on_callback_query(filters.regex(r"^tmail_"))
    async def tempmail_callback_handler(c, cq):
        data = cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data)
        parts = data.split(":")
        action = parts[0]
        user_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

        # Security check: only the owner of this mailbox can access/refresh/delete it!
        if cq.sender_id != user_id and not is_owner(cq.sender_id):
            return await cq.answer("⛔ Access denied: This temporary mailbox belongs to another user.", alert=True)

        if action == "tmail_ref":
            await cq.answer("🔄 Checking mail server...")
        elif action == "tmail_del":
            col = _get_tempmail_col()
            await col.delete_one({"user_id": user_id})
            await cq.answer("🗑 Mailbox removed from cache!", alert=True)
        elif action == "tmail_cls":
            try:
                await cq.delete()
            except (TypeError, Exception):
                try:
                    await cq.edit("<i>Mailbox panel closed.</i>", buttons=None, parse_mode="html")
                except Exception:
                    pass
            return

        text, buttons = await _render_tempmail_inbox(user_id)
        try:
            await cq.edit(text, buttons=buttons, parse_mode="html")
        except Exception:
            pass
