# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import time
import urllib.parse
from typing import Optional, Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


async def _fetch_translation(text: str, target_lang: str, source_lang: str = "auto") -> Tuple[Optional[str], str]:
    """Translate text using standard HTTP translation endpoint."""
    encoded_text = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q={encoded_text}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code == 200:
            data = res.json()
            translated_chunks = []
            detected_src = source_lang
            if data and isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], list):
                    for part in data[0]:
                        if part and len(part) > 0 and part[0]:
                            translated_chunks.append(part[0])
                if len(data) > 2 and isinstance(data[2], str):
                    detected_src = data[2]
            return "".join(translated_chunks), detected_src
    return None, source_lang


@Friday.register_on_cmd(
    ["trans", "translate", "tl"],
    cmd_help={
        "help": "Translate text or replied message to any target language code (e.g. en, es, fr, de, hi, ja, ru).",
        "example": "trans es Hello friend or trans ja (replying to message)",
    },
)
async def translate_message(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for translation.")

    raw = (m.user_input or "").strip()
    target_lang = "en"
    text_to_translate = ""

    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)

    if raw:
        parts = raw.split(" ", 1)
        if len(parts[0]) in (2, 3) and parts[0].isalpha():
            target_lang = parts[0].lower()
            if len(parts) > 1:
                text_to_translate = parts[1].strip()
        else:
            text_to_translate = raw

    if not text_to_translate and rm:
        text_to_translate = rm.text or rm.caption or ""

    if not text_to_translate:
        return await m.handle_message("❌ Please provide text to translate or reply to a text message.")

    msg = await m.handle_message(f"🌐 Translating to <b>{target_lang.upper()}</b>...")

    try:
        translated_text, src = await _fetch_translation(text_to_translate, target_lang)
        if not translated_text:
            return await msg.edit_msg("❌ Translation failed or returned empty response.")

        report = f"🌐 <b>Translation ({src.upper()} ➔ {target_lang.upper()})</b>\n\n{translated_text}"

        token = str(int(time.time() * 1000))[-8:]
        _trans_cache[token] = text_to_translate

        if "-basic" not in m.user_args and "-text" not in m.user_args:
            try:
                from Main.utils.inline_helper import send_inline_widget

                if await send_inline_widget(c, m, f"trans:{target_lang}:{token}"):
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    return
            except Exception:
                pass

        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Error during translation: <code>{e}</code>")


# ==========================================
# Interactive Inline Translation Handlers
# ==========================================

_trans_cache = {}

if getattr(Friday, "bot", None):
    import re
    from telethon import custom
    from Main.utils.custom_filters import filters
    from Main.utils.inline_helper import is_authorized_cb

    LANG_BUTTONS = [
        ("🇬🇧 EN", "en"),
        ("🇪🇸 ES", "es"),
        ("🇫🇷 FR", "fr"),
        ("🇩🇪 DE", "de"),
        ("🇮🇳 HI", "hi"),
        ("🇯🇵 JA", "ja"),
    ]

    def _make_lang_buttons(current_lang: str, token: str):
        row1 = [
            custom.Button.inline(
                f"• {label} •" if code == current_lang else label, f"tr_{code}:{token}".encode("utf-8")
            )
            for label, code in LANG_BUTTONS[:3]
        ]
        row2 = [
            custom.Button.inline(
                f"• {label} •" if code == current_lang else label, f"tr_{code}:{token}".encode("utf-8")
            )
            for label, code in LANG_BUTTONS[3:]
        ]
        return [row1, row2, [custom.Button.inline("✖ Close", b"tr_cls")]]

    @Friday.bot.on_inline_query(filters.regex(r"^trans:([a-z]{2}):(\w+)"))
    async def trans_inline_query_handler(c, iq):
        m = re.match(r"^trans:([a-z]{2}):(\w+)", iq.text)
        if not m:
            return
        target_lang = m.group(1)
        token = m.group(2)
        text = _trans_cache.get(token)
        if not text:
            return

        translated_text, src = await _fetch_translation(text, target_lang)
        if not translated_text:
            return

        report = f"🌐 <b>Translation ({src.upper()} ➔ {target_lang.upper()})</b>\n\n{translated_text}"
        buttons = _make_lang_buttons(target_lang, token)
        builder = iq.builder
        res = builder.article(
            title=f"🌐 Translated to {target_lang.upper()}",
            description="Translation with interactive quick language switcher buttons.",
            text=report,
            buttons=buttons,
            parse_mode="html",
        )
        await iq.answer([res], cache_time=0)

    @Friday.bot.on_callback_query(filters.regex(r"^tr_"))
    async def trans_callback_handler(c, cq):
        data = cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data)
        if data == "tr_cls":
            if not is_authorized_cb(cq):
                return await cq.answer("⛔ Access denied: You cannot close this widget.", alert=True)
            try:
                await cq.delete()
            except (TypeError, Exception):
                try:
                    await cq.edit("<i>Translation closed.</i>", buttons=None, parse_mode="html")
                except Exception:
                    pass
            return

        m = re.match(r"^tr_([a-z]{2}):(\w+)", data)
        if not m:
            return

        new_lang = m.group(1)
        token = m.group(2)
        text = _trans_cache.get(token)
        if not text:
            return await cq.answer("⚠️ Original translation cache expired.", alert=True)

        await cq.answer(f"🌐 Translating to {new_lang.upper()}...")
        translated_text, src = await _fetch_translation(text, new_lang)
        if not translated_text:
            return await cq.answer("❌ Translation failed.", alert=True)

        report = f"🌐 <b>Translation ({src.upper()} ➔ {new_lang.upper()})</b>\n\n{translated_text}"
        buttons = _make_lang_buttons(new_lang, token)
        try:
            await cq.edit(report, buttons=buttons, parse_mode="html")
        except Exception:
            pass
