# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

from typing import Optional, Tuple

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from XtraPlugins.ai.ai_chat import (
    _ask_ai,
    _get_cfg,
    _PROVIDER_DISPLAY,
    _DEFAULT_MODELS,
)


def _extract_text(m: Message) -> Tuple[Optional[str], Optional[str]]:
    """Extract input text from either direct argument or replied message."""
    user_input = (m.user_input or "").strip()
    replied = m.reply_to_message

    reply_text = None
    if replied:
        reply_text = (
            getattr(replied, "text", None) or getattr(replied, "caption", None) or getattr(replied, "raw_text", None)
        )

    return user_input or None, reply_text or None


async def _format_response(reply: str, chat_id: int, tool_title: str) -> str:
    cfg = await _get_cfg(chat_id)
    provider = cfg.get("provider", "groq")
    provider_label = _PROVIDER_DISPLAY.get(provider, provider)
    model = cfg.get("model") or _DEFAULT_MODELS.get(provider, "")

    header = f"⚡ <b>AI {tool_title}</b> <i>[{provider_label} · {model}]</i>\n\n"
    text = header + reply
    if len(text) > 4096:
        text = text[:4090] + "…"
    return text


@Friday.register_on_cmd(
    ["catchmeup", "recap", "chatdigest", "motocatch", "aisumm", "summarize", "aisummary"],
    cmd_help={
        "help": "'Catch Me Up' summarizer. Digest recent chat messages or summarize a replied message.",
        "example": "catchmeup (summarizes recent group chat)\n• catchmeup 50 (summarize last 50 messages)\n• .catchmeup (in reply to long message/article)\n• .aisumm <text>",
        "user_args": [
            {
                "arg": "<number>",
                "help": "Number of recent chat messages to digest (5-100, default: 30)",
                "requires_input": False,
            },
        ],
    },
)
@log_errors
async def ai_catchmeup_cmd(c: Client, m: Message):
    arg, reply = _extract_text(m)
    chat_id = m.chat_id or m.sender_id
    if reply or (arg and not arg.isdigit()):
        target = reply if reply else arg
        status = await m.handle_message("📱 <i>AI is analyzing the message…</i>")

        prompt = (
            "Deliver a high-impact, prioritized executive briefing of the provided text:\n\n"
            "⚡ **Catch Me Up — Quick Briefing**\n"
            "• 📋 **The TL;DR:** (1-2 sentences capturing the essence)\n\n"
            "🔍 **Prioritized Takeaways:**\n"
            "• (3 to 5 crisp bullet points capturing the core facts and details)\n\n"
            "💡 **Next Moves:**\n"
            "• (Key conclusion, insight, or recommended next step)\n\n"
            f'Input Text:\n"""\n{target}\n"""'
        )

        reply_content = await _ask_ai(prompt, chat_id, one_shot=True)
        text = await _format_response(reply_content, chat_id, "Catch Me Up")
        if status and hasattr(status, "edit_msg"):
            await status.edit_msg(text)
        else:
            await m.handle_message(text)
        return

    limit = 30
    if arg and arg.isdigit():
        limit = min(max(int(arg), 5), 100)

    status = await m.handle_message(f"📱 <i>Catch me up AI is reading the last {limit} messages to catch you up…</i>")

    cmd_pfx = getattr(Friday, "user_command_handler", ".") or "."
    try:
        raw_msgs = await c.get_messages(m.chat_id, limit=limit)
    except Exception as exc:
        if status and hasattr(status, "edit_msg"):
            return await status.edit_msg(f"❌ <i>Failed to fetch chat history:</i> <code>{exc}</code>")
        return await m.handle_message(f"❌ <i>Failed to fetch chat history:</i> <code>{exc}</code>")

    chat_lines = []
    for msg in reversed(raw_msgs):
        if msg.id == m.id:
            continue
        txt = getattr(msg, "text", "") or getattr(msg, "message", "") or ""
        if not txt and getattr(msg, "media", None):
            txt = "[Media / Attachment]"
        txt = txt.strip()
        if not txt:
            continue
        if any(txt.startswith(p) for p in (cmd_pfx, "/", "!", "?", "#")):
            continue
        sender = getattr(msg, "sender", None) or getattr(msg, "from_user", None)
        name = getattr(sender, "first_name", "") or getattr(msg, "post_author", "") or "Member"
        chat_lines.append(f"{name}: {txt}")

    if not chat_lines:
        if status and hasattr(status, "edit_msg"):
            return await status.edit_msg("⚠️ <i>No recent conversation text found in this chat to catch up on.</i>")
        return await m.handle_message("⚠️ <i>No recent conversation text found in this chat to catch up on.</i>")

    transcript = "\n".join(chat_lines[-60:])
    chat_title = getattr(getattr(m, "chat", None), "title", "This Chat")

    prompt = (
        f"You are'Catch Me Up' intelligent communication assistant.\n"
        f"You are catching the user up on recent messages in '{chat_title}'.\n"
        "Your mission is to deliver an executive, prioritized briefing of what happened so the user can instantly catch up without reading dozens of individual messages.\n\n"
        "Structure your briefing strictly in this clean Motorola style:\n\n"
        "⚡ **The Big Picture**\n"
        "(2-3 sentences overview of the core discussion, general tone, and main themes)\n\n"
        "🗣️ **Key Topics & Discussions**\n"
        "• **[Topic / Member]:** (Crisp breakdown of what was discussed, shared, or debated)\n\n"
        "📌 **Key Decisions & Mentions**\n"
        "• (Any agreements, shared links, answers to questions, or urgent mentions)\n\n"
        "🎯 **Next Moves**\n"
        "• (Pending questions, action points, or plans)\n\n"
        f'Chat Transcript ({len(chat_lines)} messages):\n"""\n{transcript}\n"""'
    )

    reply_content = await _ask_ai(prompt, chat_id, one_shot=True)
    text = await _format_response(reply_content, chat_id, f"Catch Me Up ({len(chat_lines)} msgs)")

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)


@Friday.register_on_cmd(
    ["aifix", "proofread", "grammar"],
    cmd_help={
        "help": "Proofread, fix grammar, and improve phrasing of text or replied message.",
        "example": "aifix (in reply to drafted email) OR .aifix <sentence>",
    },
)
@log_errors
async def ai_fix_cmd(c: Client, m: Message):
    arg, reply = _extract_text(m)
    target = reply if reply else arg
    if not target:
        return await m.handle_message(
            "❓ <b>Provide text or reply to a message to fix:</b>\n"
            "<code>.aifix &lt;text&gt;</code> or reply with <code>.aifix</code>"
        )

    chat_id = m.chat_id or m.sender_id
    status = await m.handle_message("⏳ <i>Proofreading & polishing…</i>")

    prompt = (
        "You are an expert editor and copywriter. Review the following text for grammar, punctuation, "
        "spelling, tone, and sentence flow. Output the result formatted as follows:\n\n"
        "✨ **Polished Version:**\n<the revised text>\n\n"
        "📝 **Key Improvements:**\n<brief bullet points highlighting what was corrected and why>\n\n"
        f'Input text:\n"""\n{target}\n"""'
    )

    reply_content = await _ask_ai(prompt, chat_id, one_shot=True)
    text = await _format_response(reply_content, chat_id, "Proofreader")

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)


@Friday.register_on_cmd(
    ["aiexplain", "explain", "codeexplain"],
    cmd_help={
        "help": "Explain code snippets, algorithms, complex concepts, or jargon in simple terms.",
        "example": "aiexplain (reply to code) OR .aiexplain Quantum entanglement",
    },
)
@log_errors
async def ai_explain_cmd(c: Client, m: Message):
    arg, reply = _extract_text(m)
    target = reply if reply else arg
    if not target:
        return await m.handle_message(
            "❓ <b>Provide a topic/code or reply to a message to explain:</b>\n"
            "<code>.aiexplain &lt;concept or code&gt;</code>"
        )

    chat_id = m.chat_id or m.sender_id
    status = await m.handle_message("⏳ <i>Analyzing & formulating explanation…</i>")

    prompt = (
        "You are a master teacher and engineer. Explain the following concept or code clearly, "
        "elegantly, and intuitively:\n"
        "• If it is code: explain what it does, potential edge cases/bugs, and time/space complexity.\n"
        "• If it is a concept: explain it like I am smart but new to the field, with an analogy.\n\n"
        f'Content to explain:\n"""\n{target}\n"""'
    )

    reply_content = await _ask_ai(prompt, chat_id, one_shot=True)
    text = await _format_response(reply_content, chat_id, "Explainer")

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)


@Friday.register_on_cmd(
    ["airoast", "roast"],
    cmd_help={
        "help": "Playfully roast the replied message or user with savage wit.",
        "example": "airoast (reply to someone)",
    },
)
@log_errors
async def ai_roast_cmd(c: Client, m: Message):
    arg, reply = _extract_text(m)
    target = reply if reply else arg
    if not target:
        return await m.handle_message("❓ <b>Reply to a message to roast it!</b>")

    chat_id = m.chat_id or m.sender_id
    status = await m.handle_message("🔥 <i>Heating up the grill…</i>")

    prompt = (
        "You are a stand-up comedian participating in a roast battle. Deliver a hilarious, "
        "sarcastic, sharp, and witty roast targeting the following message or opinion.\n"
        "Rules: Be funny and savage, but do NOT use slurs, hate speech, or explicit NSFW content.\n\n"
        f'Message to roast:\n"""\n{target}\n"""'
    )

    reply_content = await _ask_ai(prompt, chat_id, one_shot=True)
    text = await _format_response(reply_content, chat_id, "Roast 🔥")

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)


@Friday.register_on_cmd(
    ["aitl", "aitranslate"],
    cmd_help={
        "help": "Translate text or replied message using AI with natural phrasing and tone preservation.",
        "example": "aitl spanish (in reply) OR .aitl japanese Good morning friend",
    },
)
@log_errors
async def ai_translate_cmd(c: Client, m: Message):
    arg, reply = _extract_text(m)

    target_lang = "English"
    target_text = ""

    if reply:
        # If replying, arg can specify target language
        target_lang = arg if arg else "English"
        target_text = reply
    elif arg:
        parts = arg.split(maxsplit=1)
        if len(parts) == 1:
            # Just text -> translate to English
            target_text = parts[0]
            target_lang = "English"
        else:
            # First word might be target language
            target_lang = parts[0]
            target_text = parts[1]
    else:
        return await m.handle_message(
            "❓ <b>Usage:</b>\n"
            "• Reply to message: <code>.aitl [language]</code>\n"
            "• Direct text: <code>.aitl [language] &lt;text&gt;</code>"
        )

    chat_id = m.chat_id or m.sender_id
    status = await m.handle_message(f"🌐 <i>Translating into {target_lang}…</i>")

    prompt = (
        f"You are a world-class professional translator. Translate the following text into **{target_lang}**.\n"
        "Requirements:\n"
        "• Preserve the emotional tone, idioms, and natural phrasing.\n"
        "• Provide the translated text clearly.\n"
        "• If applicable, note pronunciation or cultural context briefly.\n\n"
        f'Text to translate:\n"""\n{target_text}\n"""'
    )

    reply_content = await _ask_ai(prompt, chat_id, one_shot=True)
    text = await _format_response(reply_content, chat_id, f"Translator [{target_lang}]")

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)


@Friday.register_on_cmd(
    ["aiask", "quickai"],
    cmd_help={
        "help": "Ask a quick one-shot question without storing it in chat history.",
        "example": "aiask What is the speed of light in vacuum?",
    },
    requires_input=True,
)
@log_errors
async def ai_one_shot_cmd(c: Client, m: Message):
    prompt = (m.user_input or "").strip()
    if not prompt:
        return await m.handle_message("❓ <i>Provide a question:</i> <code>.aiask &lt;prompt&gt;</code>")

    chat_id = m.chat_id or m.sender_id
    status = await m.handle_message("⚡ <i>Thinking…</i>")

    reply = await _ask_ai(prompt, chat_id, one_shot=True)
    text = await _format_response(reply, chat_id, "Quick Query")

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)
