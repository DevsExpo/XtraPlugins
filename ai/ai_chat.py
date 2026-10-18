# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import html
import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors, iuser_check
from Main.utils.custom_filters import filters, create
from telethon import custom

logger = logging.getLogger("friday.ai_chat")


_MAX_HISTORY = 10  # rolling window of message pairs
_EDIT_INTERVAL = 1.5  # seconds between progressive edits (streaming feel)
_COLLECTION = "AI_CHAT"  # DB collection name


_DEFAULT_MODELS: Dict[str, str] = {
    "groq": "qwen/qwen3.8-27b",
    "gemini": "gemini-1.5-flash",
    "ollama": "llama3.2",
}

_PROVIDER_DISPLAY: Dict[str, str] = {
    "groq": "⚡ Groq",
    "gemini": "✨ Gemini",
    "ollama": "🏠 Ollama (local)",
}

_MODEL_ALIASES: Dict[str, Dict[str, str]] = {
    "groq": {
        "fast": "qwen/qwen3.8-27b",
        "qwen": "qwen/qwen3.8-27b",
        "default": "qwen/qwen3.8-27b",
        "smart": "openai/gpt-oss-120b",
        "120b": "openai/gpt-oss-120b",
        "gpt120b": "openai/gpt-oss-120b",
        "20b": "openai/gpt-oss-20b",
        "gpt20b": "openai/gpt-oss-20b",
        "llama": "llama-3.3-70b-versatile",
        "llama3": "llama-3.3-70b-versatile",
        "70b": "llama-3.3-70b-versatile",
        "8b": "llama-3.1-8b-instant",
        # Legacy/decommissioned Groq mappings
        "llama3-8b-8192": "qwen/qwen3.8-27b",
        "llama3-70b-8192": "openai/gpt-oss-120b",
        "llama-3.1-70b-versatile": "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768": "qwen/qwen3.8-27b",
        "gemma2-9b-it": "qwen/qwen3.8-27b",
    },
    "gemini": {
        "flash": "gemini-1.5-flash",
        "pro": "gemini-1.5-pro",
        "2.0": "gemini-2.0-flash",
        "flash2": "gemini-2.0-flash",
        "gemini-pro": "gemini-1.5-pro",
        "default": "gemini-1.5-flash",
    },
    "ollama": {
        "llama": "llama3.2",
        "llama3": "llama3.2",
        "qwen": "qwen2.5",
        "mistral": "mistral",
        "default": "llama3.2",
    },
}

_DEFAULT_AUTOCHAT_SYSTEM = (
    "You are a friendly, witty, and natural participant in a Telegram chat. "
    "Keep responses concise (1-3 sentences for casual chat), natural, and engaging. "
    "Understand emojis, internet slang, and regional languages (like Tamil, Hindi, Spanish, etc.). "
    "Do not sound like a robotic corporate assistant or customer support agent."
)

_GROQ_MODELS_CACHE: Dict[str, Any] = {"models": [], "expires_at": 0}


def _resolve_model(provider: str, model: Optional[str]) -> str:
    """Normalize model names, resolving aliases and decommissioned models to active defaults."""
    default = _DEFAULT_MODELS.get(provider, "default")
    if not model or model.strip().lower() in ("default", "none", "auto", ""):
        return default
    cleaned = model.strip()
    lowered = cleaned.lower()
    provider_aliases = _MODEL_ALIASES.get(provider, {})
    if lowered in provider_aliases:
        return provider_aliases[lowered]
    return cleaned


async def _get_available_groq_models(client: Any) -> List[str]:
    """Retrieve and cache active chat models available on Groq."""
    now = time.time()
    if _GROQ_MODELS_CACHE["models"] and now < _GROQ_MODELS_CACHE["expires_at"]:
        return _GROQ_MODELS_CACHE["models"]
    try:
        models_resp = await client.models.list()
        chat_models = []
        for m in getattr(models_resp, "data", []):
            m_id = str(getattr(m, "id", ""))
            lowered = m_id.lower()
            if any(skip in lowered for skip in ("whisper", "guard", "audio", "vision", "safeguard")):
                continue
            chat_models.append(m_id)
        if chat_models:
            _GROQ_MODELS_CACHE["models"] = chat_models
            _GROQ_MODELS_CACHE["expires_at"] = now + 3600
            return chat_models
    except Exception as exc:
        logger.warning(f"Failed to list Groq models: {exc}")
    return _GROQ_MODELS_CACHE.get("models") or ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]


async def _detect_best_provider() -> str:
    """Intelligently detect available AI provider based on saved API keys and connectivity."""
    groq_key = await Friday.config.get_env("GROQ_API_KEY")
    if groq_key:
        return "groq"
    gemini_key = await Friday.config.get_env("GEMINI_API_KEY")
    if gemini_key:
        return "gemini"
    ollama_url = await Friday.config.get_env("OLLAMA_URL")
    if ollama_url:
        return "ollama"
    return "groq"


def _col():
    """Retrieve the AI_CHAT collection from Friday's database."""
    if Friday.db is not None:
        return Friday.db.make_collection(_COLLECTION)
    return None


async def _get_cfg(chat_id: Union[int, str]) -> Dict[str, Any]:
    """Fetch AI config for the given chat/user. Falls back to global default and active providers."""
    col = _col()
    doc = None
    if col is not None:
        doc = await col.find_one({"_id": f"cfg_{chat_id}"})
        if not doc:
            doc = await col.find_one({"_id": "cfg_global"})

    provider = doc.get("provider") if doc else None
    if not provider:
        provider = await _detect_best_provider()

    raw_model = doc.get("model") if doc else None
    model = _resolve_model(provider, raw_model)

    return {
        "provider": provider,
        "model": model,
        "system": doc.get("system") if doc else None,
    }


async def _set_cfg(chat_id: Union[int, str], **kwargs: Any) -> None:
    """Persist AI settings for chat and update global default in DB."""
    col = _col()
    if col is None:
        return
    await col.find_one_and_update(
        {"_id": f"cfg_{chat_id}"},
        {"$set": kwargs},
        upsert=True,
    )
    # Also update global fallback configuration in DB
    await col.find_one_and_update(
        {"_id": "cfg_global"},
        {"$set": kwargs},
        upsert=True,
    )


async def _get_history(chat_id: Union[int, str]) -> List[Dict[str, str]]:
    """Retrieve rolling conversation history from DB."""
    col = _col()
    if col is None:
        return []
    doc = await col.find_one({"_id": f"hist_{chat_id}"})
    return doc.get("history", []) if doc else []


async def _push_history(chat_id: Union[int, str], user_msg: str, ai_msg: str) -> None:
    """Append a user/assistant pair and trim to _MAX_HISTORY pairs in DB."""
    col = _col()
    if col is None:
        return
    history = await _get_history(chat_id)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": ai_msg})
    # Keep last N * 2 entries (N pairs)
    history = history[-((_MAX_HISTORY) * 2) :]
    await col.find_one_and_update(
        {"_id": f"hist_{chat_id}"},
        {"$set": {"history": history}},
        upsert=True,
    )


async def _clear_history(chat_id: Union[int, str]) -> None:
    """Delete conversation history from DB."""
    col = _col()
    if col is None:
        return
    await col.find_one_and_delete({"_id": f"hist_{chat_id}"})


# ─── Database-Backed Auto-Chat State & Cooldowns ──────────────────────────────


async def _check_and_update_cooldown(
    chat_id: Union[int, str],
    sender_id: Union[int, str],
    cooldown_seconds: float = 1.5,
) -> bool:
    """
    Checks and updates per-chat/sender cooldown directly in the database.
    Returns True if allowed to reply, False if still cooling down.
    """
    col = _col()
    if col is None:
        return True
    now = time.time()
    doc_id = f"autochat_cooldown_{chat_id}_{sender_id}"
    doc = await col.find_one({"_id": doc_id})
    if doc:
        last_time = doc.get("last_replied_at", 0)
        if now - last_time < cooldown_seconds:
            return False  # Still on cooldown

    await col.find_one_and_update(
        {"_id": doc_id},
        {
            "$set": {
                "type": "autochat_cooldown",
                "chat_id": chat_id,
                "sender_id": sender_id,
                "last_replied_at": now,
            }
        },
        upsert=True,
    )
    return True


async def _is_user_autochat_enabled(user_id: int) -> bool:
    """Check database if auto-chat is enabled for this user."""
    col = _col()
    if col is None:
        return False
    doc = await col.find_one({"_id": f"autochat_user_{user_id}", "enabled": True})
    return bool(doc)


async def _get_chat_autochat_info(chat_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve auto-chat configuration for a group/channel from DB."""
    col = _col()
    if col is None:
        return None
    return await col.find_one({"_id": f"autochat_chat_{chat_id}", "enabled": True})


async def _toggle_user_autochat(user_id: int, name: str, enable: Optional[bool] = None) -> bool:
    """Toggle or explicitly set auto-chat for a user in the database."""
    col = _col()
    if col is None:
        return False
    doc_id = f"autochat_user_{user_id}"
    existing = await col.find_one({"_id": doc_id})
    current_enabled = existing.get("enabled", False) if existing else False
    new_state = (not current_enabled) if enable is None else enable

    if new_state:
        await col.find_one_and_update(
            {"_id": doc_id},
            {
                "$set": {
                    "type": "autochat_user",
                    "user_id": user_id,
                    "name": name,
                    "enabled": True,
                    "updated_at": int(time.time()),
                }
            },
            upsert=True,
        )
    else:
        await col.find_one_and_delete({"_id": doc_id})

    return new_state


async def _toggle_chat_autochat(
    chat_id: int,
    title: str,
    mode: str = "reply",
    enable: Optional[bool] = None,
) -> Tuple[bool, str]:
    """Toggle or explicitly set auto-chat for a group/channel in the database."""
    col = _col()
    if col is None:
        return False, mode
    doc_id = f"autochat_chat_{chat_id}"
    existing = await col.find_one({"_id": doc_id})
    current_enabled = existing.get("enabled", False) if existing else False
    current_mode = existing.get("mode", mode) if existing else mode
    new_state = (not current_enabled) if enable is None else enable

    if new_state:
        final_mode = mode if enable is not None else current_mode
        await col.find_one_and_update(
            {"_id": doc_id},
            {
                "$set": {
                    "type": "autochat_chat",
                    "chat_id": chat_id,
                    "title": title,
                    "mode": final_mode,
                    "enabled": True,
                    "updated_at": int(time.time()),
                }
            },
            upsert=True,
        )
        return True, final_mode
    else:
        await col.find_one_and_delete({"_id": doc_id})
        return False, current_mode


async def _clear_all_autochat() -> int:
    """Clear all auto-chat targets and cooldown records from the database."""
    col = _col()
    if col is None:
        return 0
    res = await col.delete_many({"type": {"$in": ["autochat_user", "autochat_chat", "autochat_cooldown"]}})
    return getattr(res, "deleted_count", 0)


async def _get_autochat_list() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Retrieve all active user and chat auto-chat targets directly from the database."""
    col = _col()
    if col is None:
        return [], []
    cursor = col.find({"type": {"$in": ["autochat_user", "autochat_chat"]}, "enabled": True})
    docs = await cursor.to_list(length=500) if hasattr(cursor, "to_list") else [d async for d in cursor]
    users = [d for d in docs if d.get("type") == "autochat_user"]
    chats = [d for d in docs if d.get("type") == "autochat_chat"]
    return users, chats


async def _call_groq(
    prompt: str,
    history: List[Dict[str, str]],
    system: Optional[str],
    model: Optional[str],
) -> str:
    try:
        from groq import AsyncGroq  # type: ignore[import]
    except ImportError:
        return "❌ <b>Groq not installed.</b>\nRun: <code>pip install groq</code>"

    api_key = await Friday.config.get_env("GROQ_API_KEY")
    if not api_key:
        return (
            "❌ <b>GROQ_API_KEY not set.</b>\n\n"
            "Get a free key at <a href='https://console.groq.com'>console.groq.com</a> "
            "and add it: <code>.aiset apikey &lt;key&gt;</code>"
        )

    chosen_model = _resolve_model("groq", model)
    effective_system = system or _DEFAULT_AUTOCHAT_SYSTEM
    messages: List[Dict[str, str]] = []
    if effective_system:
        messages.append({"role": "system", "content": effective_system})
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    client = AsyncGroq(api_key=api_key)
    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=chosen_model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip()
            return "🤔 No response received."
        except Exception as exc:
            err_str = str(exc).lower()
            if attempt == 0 and ("decommissioned" in err_str or "not_found" in err_str or "does not exist" in err_str):
                active_models = await _get_available_groq_models(client)
                fallback = (
                    "qwen/qwen3.8-27b"
                    if "qwen/qwen3.8-27b" in active_models
                    else (active_models[0] if active_models else _DEFAULT_MODELS["groq"])
                )
                logger.warning(f"Groq model '{chosen_model}' unavailable ({exc}). Auto-switching to '{fallback}'")
                chosen_model = fallback
                continue
            logger.error(f"Groq error: {exc}")
            return f"❌ <b>Groq error:</b> <code>{html.escape(str(exc)[:300])}</code>"


async def _call_gemini(
    prompt: str,
    history: List[Dict[str, str]],
    system: Optional[str],
    model: Optional[str],
) -> str:
    try:
        import google.generativeai as genai  # type: ignore[import]
    except ImportError:
        return "❌ <b>google-generativeai not installed.</b>\nRun: <code>pip install google-generativeai</code>"

    api_key = await Friday.config.get_env("GEMINI_API_KEY")
    if not api_key:
        return (
            "❌ <b>GEMINI_API_KEY not set.</b>\n\n"
            "Get a free key at <a href='https://aistudio.google.com/app/apikey'>AI Studio</a> "
            "and add: <code>.aiset apikey &lt;key&gt;</code>"
        )

    genai.configure(api_key=api_key)
    chosen_model = _resolve_model("gemini", model)

    # Build Gemini history format
    gemini_history = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [msg["content"]]})

    sys_instruction = system or _DEFAULT_AUTOCHAT_SYSTEM
    try:
        gen_model = genai.GenerativeModel(
            model_name=chosen_model,
            system_instruction=sys_instruction,
        )
        chat_session = gen_model.start_chat(history=gemini_history)
        response = await asyncio.get_event_loop().run_in_executor(None, chat_session.send_message, prompt)
        return response.text or "🤔 No response received."
    except Exception as exc:
        logger.error(f"Gemini error: {exc}")
        return f"❌ <b>Gemini error:</b> <code>{html.escape(str(exc)[:300])}</code>"


async def _call_ollama(
    prompt: str,
    history: List[Dict[str, str]],
    system: Optional[str],
    model: Optional[str],
) -> str:
    import httpx

    base_url = await Friday.config.get_env("OLLAMA_URL") or "http://localhost:11434"
    chosen_model = _resolve_model("ollama", model)
    effective_system = system or _DEFAULT_AUTOCHAT_SYSTEM

    messages: List[Dict[str, str]] = []
    if effective_system:
        messages.append({"role": "system", "content": effective_system})
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.post(
                f"{base_url}/api/chat",
                json={"model": chosen_model, "messages": messages, "stream": False},
            )
        if resp.status_code != 200:
            return f"❌ <b>Ollama returned HTTP {resp.status_code}</b>\nIs Ollama running at <code>{base_url}</code>?"
        data = resp.json()
        return data.get("message", {}).get("content") or "🤔 No response received."
    except httpx.ConnectError:
        return (
            f"❌ <b>Cannot connect to Ollama</b> at <code>{base_url}</code>\n"
            "Make sure Ollama is running: <code>ollama serve</code>"
        )
    except Exception as exc:
        logger.error(f"Ollama error: {exc}")
        return f"❌ <b>Ollama error:</b> <code>{html.escape(str(exc)[:300])}</code>"


async def _ask_ai(
    prompt: str,
    chat_id: Union[int, str],
    one_shot: bool = False,
) -> str:
    """Route prompt to the configured provider and return text response."""
    cfg = await _get_cfg(chat_id)
    provider = cfg.get("provider", "groq")
    model = cfg.get("model")
    system = cfg.get("system")
    history = [] if one_shot else await _get_history(chat_id)

    if provider == "groq":
        reply = await _call_groq(prompt, history, system, model)
    elif provider == "gemini":
        reply = await _call_gemini(prompt, history, system, model)
    elif provider == "ollama":
        reply = await _call_ollama(prompt, history, system, model)
    else:
        reply = f"❌ Unknown provider: <code>{html.escape(provider)}</code>"

    if not one_shot and not reply.startswith("❌"):
        await _push_history(chat_id, prompt, reply)

    return reply


@Friday.register_on_cmd(
    ["ai", "ask"],
    cmd_help={
        "help": "Chat with AI (Groq / Gemini / Ollama). Reply to a message or provide prompt.",
        "example": "ai What is the Riemann hypothesis?\n(or reply to a message with .ai)",
    },
    requires_input=False,
)
@log_errors
async def ai_chat_cmd(c: Client, m: Message):
    prompt = (m.user_input or "").strip()
    replied = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)

    replied_text = ""
    if replied:
        replied_text = (
            getattr(replied, "text", None)
            or getattr(replied, "caption", None)
            or getattr(replied, "raw_text", "")
            or ""
        ).strip()

    if not prompt and not replied_text:
        return await m.handle_message(
            "❓ <b>AI Chat Usage:</b>\n\n"
            "• <code>.ai &lt;question&gt;</code> — Ask AI anything\n"
            "• Reply to any message with <code>.ai</code> — AI replies to that message\n"
            "• Reply to a message with <code>.ai &lt;query&gt;</code> — AI analyzes that message\n"
            "• <code>.aichat</code> — Toggle persistent DB auto-chat for user or group"
        )

    if replied_text and prompt:
        full_prompt = f'Replying to: "{replied_text}"\n\nQuestion/Instruction: {prompt}'
    elif replied_text:
        full_prompt = f'Respond conversationally to this message: "{replied_text}"'
    else:
        full_prompt = prompt

    chat_id = m.chat_id or m.sender_id
    status = await m.handle_message("⏳ <i>Thinking…</i>")
    reply = await _ask_ai(full_prompt, chat_id)

    cfg = await _get_cfg(chat_id)
    provider = cfg.get("provider", "groq")
    provider_label = _PROVIDER_DISPLAY.get(provider, provider)
    model = cfg.get("model") or _DEFAULT_MODELS.get(provider, "")
    header = f"🤖 <b>AI</b> <i>[{provider_label} · {model}]</i>\n\n"

    text = header + reply
    if len(text) > 4096:
        text = text[:4090] + "…"

    if status and hasattr(status, "edit_msg"):
        await status.edit_msg(text)
    else:
        await m.handle_message(text)


@Friday.register_on_cmd(
    ["aichat", "autochat"],
    cmd_help={
        "help": "Toggle persistent AI auto-chat in DB for a user (reply to their message) or for a group.",
        "example": "aichat (in reply to user, or in a group)",
        "user_args": [
            {"arg": "on", "help": "Force enable auto-chat for this user or group", "requires_input": False},
            {"arg": "off", "help": "Force disable auto-chat for this user or group", "requires_input": False},
            {"arg": "mode", "help": "Set group mode: .aichat mode reply | all", "requires_input": True},
            {"arg": "list", "help": "List active auto-chat targets from DB", "requires_input": False},
            {"arg": "clear", "help": "Clear all auto-chat targets from DB", "requires_input": False},
        ],
    },
)
@log_errors
async def ai_autochat_cmd(c: Client, m: Message):
    raw_args = (m.user_input or "").strip()
    parts = raw_args.split(None, 1)
    sub = parts[0].lower() if parts else ""
    sub_val = parts[1].strip() if len(parts) > 1 else ""

    # Subcommand: list
    if sub in ("list", "all_active", "status"):
        users, chats = await _get_autochat_list()
        if not users and not chats:
            return await m.handle_message(
                "🤖 <b>AI Auto-Chat Targets (Database)</b>\n\n"
                "<i>No active auto-chat targets found in DB.</i>\n\n"
                "• Reply to a user with <code>.aichat</code> to auto-chat with them.\n"
                "• Use <code>.aichat</code> in a group to auto-chat in the group."
            )
        lines = ["🤖 <b>Active AI Auto-Chat Targets (Database)</b>\n"]
        if users:
            lines.append(f"👥 <b>Users ({len(users)}):</b>")
            for u in users:
                lines.append(
                    f"• <a href='tg://user?id={u['user_id']}'>{html.escape(u.get('name', 'User'))}</a> (<code>{u['user_id']}</code>)"
                )
            lines.append("")
        if chats:
            lines.append(f"📢 <b>Groups / Chats ({len(chats)}):</b>")
            for ch in chats:
                mode_str = ch.get("mode", "reply")
                lines.append(
                    f"• <b>{html.escape(ch.get('title', 'Group'))}</b> (<code>{ch['chat_id']}</code>) — Mode: <code>{mode_str}</code>"
                )
            lines.append("")
        lines.append("<i>Toggle off anytime by replying or typing <code>.aichat</code> in the chat.</i>")
        return await m.handle_message("\n".join(lines))

    # Subcommand: clear
    if sub in ("clear", "reset_all"):
        count = await _clear_all_autochat()
        return await m.handle_message(f"🗑️ <b>Cleared all AI Auto-Chat targets from DB ({count} records deleted).</b>")

    # Subcommand: mode <reply|all>
    if sub == "mode":
        if not (m.is_group or m.is_channel):
            return await m.handle_message("❌ <code>.aichat mode</code> can only be used in a group or channel.")
        target_mode = sub_val.lower()
        if target_mode not in ("reply", "all"):
            return await m.handle_message(
                "❌ Invalid mode. Choose <code>reply</code> or <code>all</code>:\n"
                "• <code>.aichat mode reply</code> (replies to userbot or @mentions)\n"
                "• <code>.aichat mode all</code> (chats on every message)"
            )
        chat_id = m.chat_id
        chat_title = getattr(m.chat, "title", f"Chat {chat_id}")
        await _toggle_chat_autochat(chat_id, chat_title, mode=target_mode, enable=True)
        return await m.handle_message(
            f"⚙️ <b>Auto-Chat mode for {html.escape(chat_title)} saved in DB:</b> <code>{target_mode}</code>\n"
            f"<i>{('Responds to every incoming message.' if target_mode == 'all' else 'Responds when replied to or mentioned.')}</i>"
        )

    # Determine desired action: on, off, or toggle
    desired_enable: Optional[bool] = None
    if sub in ("on", "enable", "start"):
        desired_enable = True
    elif sub in ("off", "disable", "stop"):
        desired_enable = False

    replied = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    my_id = getattr(c.myself, "id", None) if getattr(c, "myself", None) else None

    # Scenario 1: Replied to a user
    if replied and replied.sender_id:
        target_id = replied.sender_id
        if my_id and target_id == my_id:
            return await m.handle_message("⚠️ <i>Cannot enable auto-chat on your own messages.</i>")

        target_sender = getattr(replied, "sender", None) or getattr(replied, "from_user", None)
        first_name = getattr(target_sender, "first_name", "") or ""
        last_name = getattr(target_sender, "last_name", "") or ""
        target_name = (
            f"{first_name} {last_name}".strip() or getattr(target_sender, "username", "") or f"User {target_id}"
        )

        new_state = await _toggle_user_autochat(target_id, target_name, enable=desired_enable)
        if new_state:
            return await m.handle_message(
                f"🤖 <b>AI Auto-Chat ENABLED (DB):</b>\n"
                f"👤 <b>{html.escape(target_name)}</b> (<code>{target_id}</code>)\n\n"
                f"<i>Friday will now automatically respond to their messages!</i>\n"
                f"<i>Tip: Reply again with <code>.aichat</code> or <code>.aichat off</code> to stop.</i>"
            )
        else:
            return await m.handle_message(
                f"🛑 <b>AI Auto-Chat DISABLED (DB):</b>\n"
                f"👤 <b>{html.escape(target_name)}</b> (<code>{target_id}</code>)"
            )

    # Scenario 2: In a private chat (DM) without replying to another message
    if m.is_private:
        target_id = m.chat_id or m.sender_id
        if my_id and target_id == my_id:
            return await m.handle_message("⚠️ <i>Cannot enable auto-chat in Saved Messages.</i>")

        target_sender = getattr(m, "chat", None) or getattr(m, "sender", None)
        first_name = getattr(target_sender, "first_name", "") or ""
        last_name = getattr(target_sender, "last_name", "") or ""
        target_name = (
            f"{first_name} {last_name}".strip() or getattr(target_sender, "username", "") or f"User {target_id}"
        )

        new_state = await _toggle_user_autochat(target_id, target_name, enable=desired_enable)
        if new_state:
            return await m.handle_message(
                f"🤖 <b>AI Auto-Chat ENABLED for this chat (DB):</b>\n"
                f"👤 <b>{html.escape(target_name)}</b> (<code>{target_id}</code>)\n\n"
                f"<i>Friday will now automatically reply to messages here!</i>"
            )
        else:
            return await m.handle_message(
                f"🛑 <b>AI Auto-Chat DISABLED for this chat (DB):</b>\n"
                f"👤 <b>{html.escape(target_name)}</b> (<code>{target_id}</code>)"
            )

    # Scenario 3: In a group or channel
    if m.is_group or m.is_channel:
        chat_id = m.chat_id
        chat_title = getattr(m.chat, "title", f"Chat {chat_id}")
        new_state, mode = await _toggle_chat_autochat(chat_id, chat_title, enable=desired_enable)
        if new_state:
            mode_desc = "Responds when replied to or mentioned." if mode == "reply" else "Responds to all messages."
            return await m.handle_message(
                f"🤖 <b>AI Auto-Chat ENABLED for group (DB):</b>\n"
                f"📢 <b>{html.escape(chat_title)}</b> (<code>{chat_id}</code>)\n"
                f"⚙️ <b>Mode:</b> <code>{mode}</code> <i>({mode_desc})</i>\n\n"
                f"• Use <code>.aichat mode all</code> to chat on every message.\n"
                f"• Use <code>.aichat off</code> or reply with <code>.aichat</code> to disable."
            )
        else:
            return await m.handle_message(
                f"🛑 <b>AI Auto-Chat DISABLED for this group (DB):</b>\n"
                f"📢 <b>{html.escape(chat_title)}</b> (<code>{chat_id}</code>)"
            )

    await m.handle_message(
        "❓ <b>Usage:</b>\n"
        "• Reply to a user with <code>.aichat</code> to auto-chat with them\n"
        "• Run <code>.aichat</code> in a group to auto-chat in that group\n"
        "• <code>.aichat mode &lt;reply|all&gt;</code> — switch group mode\n"
        "• <code>.aichat list</code> — view active auto-chats from DB\n"
        "• <code>.aichat clear</code> — disable all in DB"
    )


# ─── Background Auto-Chat Message Listener ───────────────────────────────────


async def autochat_filter(c: Client, m: Message) -> bool:
    """Filter querying DB to determine if an incoming message triggers AI auto-chat."""
    col = _col()
    if col is None:
        return False

    # Skip outgoing messages unless in self-test mode
    if getattr(m, "out", False) and not getattr(Friday, "self_test_mode", False):
        return False

    # Must contain text or caption
    txt = (getattr(m, "text", None) or getattr(m, "caption", None) or getattr(m, "raw_text", "") or "").strip()
    if not txt:
        return False

    # Skip commands
    cmd_pfx = getattr(Friday, "user_command_handler", ".") or "."
    if any(txt.startswith(p) for p in (cmd_pfx, "/", "!", "?", "#")):
        return False

    my_id = getattr(c.myself, "id", None) if getattr(c, "myself", None) else None
    sender_id = m.sender_id or (getattr(m.from_user, "id", None) if getattr(m, "from_user", None) else None)
    if my_id and sender_id == my_id:
        return False

    # Ignore bot senders to prevent infinite bot loops
    sender = getattr(m, "sender", None) or getattr(m, "from_user", None)
    if sender and getattr(sender, "bot", False):
        return False

    chat_id = m.chat_id or (getattr(m.chat, "id", None) if getattr(m, "chat", None) else sender_id)
    if not chat_id:
        return False

    # Trigger Condition 1: Check DB if sender is explicitly enabled for auto-chat
    if sender_id and await _is_user_autochat_enabled(sender_id):
        return True

    # Trigger Condition 2: Check DB if current chat/group has auto-chat enabled
    chat_doc = await _get_chat_autochat_info(chat_id)
    if chat_doc:
        mode = chat_doc.get("mode", "reply")
        if mode == "all":
            return True
        # In DM, private chat with autochat enabled always responds
        if m.is_private:
            return True
        # In group, check if mentioned
        if getattr(m, "mentioned", False):
            return True
        my_uname = getattr(c.myself, "username", "") if getattr(c, "myself", None) else ""
        if my_uname and f"@{my_uname.lower()}" in txt.lower():
            return True
        # In group, check if message is a reply to the userbot
        replied_msg = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
        if replied_msg:
            reply_sender = getattr(replied_msg, "sender_id", None)
            if (my_id and reply_sender == my_id) or getattr(replied_msg, "out", False):
                return True

    return False


@Friday.on_message(
    create(autochat_filter),
    group=5,
    bot_mode_unsupported=True,
)
@log_errors
async def autochat_listener(c: Client, m: Message):
    """Processes messages matching DB auto-chat filter and delivers conversational AI replies."""
    chat_id = m.chat_id or (getattr(m.chat, "id", None) if getattr(m, "chat", None) else m.sender_id)
    sender_id = m.sender_id or (getattr(m.from_user, "id", None) if getattr(m, "from_user", None) else None)

    # Check and update cooldown directly in the database
    if not await _check_and_update_cooldown(chat_id, sender_id, cooldown_seconds=1.5):
        return

    user_text = (getattr(m, "text", None) or getattr(m, "caption", None) or getattr(m, "raw_text", "") or "").strip()
    if not user_text:
        return

    # Strip bot username mention if present for cleaner AI understanding
    clean_text = user_text
    my_uname = getattr(c.myself, "username", "") if getattr(c, "myself", None) else ""
    if my_uname:
        clean_text = re.sub(rf"@{my_uname}\b", "", clean_text, flags=re.IGNORECASE).strip()
        if not clean_text:
            clean_text = user_text

    # Show Telegram typing status and fetch response
    try:
        async with c.action(chat_id, "typing"):
            reply = await _ask_ai(clean_text, chat_id=chat_id)
    except Exception:
        reply = await _ask_ai(clean_text, chat_id=chat_id)

    # Suppress errors/empty replies in auto-chat so chat isn't spammed
    if not reply or reply.startswith("❌"):
        logger.warning(f"Auto-chat error in {chat_id}: {reply}")
        return

    # Enforce Telegram 4096 char limit
    if len(reply) > 4096:
        reply = reply[:4090] + "…"

    # Reply to the user
    try:
        await m.reply_msg(reply)
    except Exception as exc:
        logger.error(f"Failed to reply_msg in auto-chat: {exc}")
        try:
            await c.send_message(chat_id, reply, reply_to=m.id)
        except Exception as e2:
            logger.error(f"Failed to send_message fallback in auto-chat: {e2}")


async def _show_available_models(m: Message, provider: str, current_model: Optional[str]):
    current = current_model or _DEFAULT_MODELS.get(provider, "")
    cmd_pfx = getattr(Friday, "user_command_handler", ".") or "."
    if isinstance(cmd_pfx, (list, tuple)):
        cmd_pfx = cmd_pfx[0]

    if provider == "groq":
        lines = [
            "⚡ <b>Available Groq Models</b>",
            f"<i>Current active model:</i> <code>{html.escape(current)}</code>\n",
            "<b>Top Recommended Models:</b>",
            "• <code>qwen/qwen3.8-27b</code> (Alias: <code>fast</code> / <code>qwen</code>) — <i>Ultra-fast (0.14s), multilingual, 131k ctx</i> ⚡ <b>[Default]</b>",
            "• <code>openai/gpt-oss-120b</code> (Alias: <code>smart</code> / <code>120b</code>) — <i>Flagship 120B model, deep reasoning</i> 🧠",
            "• <code>openai/gpt-oss-20b</code> (Alias: <code>20b</code>) — <i>Compact reasoning model, fast response</i>",
            "",
            "<b>Quick Switch Commands:</b>",
            f"• <code>{cmd_pfx}aiset model fast</code> — Switch to Qwen 27B (instant)",
            f"• <code>{cmd_pfx}aiset model 120b</code> — Switch to GPT 120B (smartest)",
            f"• <code>{cmd_pfx}aiset model 20b</code> — Switch to GPT 20B",
            f"• <code>{cmd_pfx}aiset model &lt;model_id&gt;</code> — Set any custom model",
        ]
        return await m.handle_message("\n".join(lines))
    elif provider == "gemini":
        lines = [
            "✨ <b>Available Gemini Models</b>",
            f"<i>Current active model:</i> <code>{html.escape(current)}</code>\n",
            "<b>Recommended Models:</b>",
            "• <code>gemini-1.5-flash</code> (Alias: <code>flash</code>) — <i>Fast, high throughput</i> ⚡ <b>[Default]</b>",
            "• <code>gemini-1.5-pro</code> (Alias: <code>pro</code>) — <i>Deep reasoning, huge context</i> 🧠",
            "• <code>gemini-2.0-flash</code> (Alias: <code>2.0</code>) — <i>Next-generation multimodal</i> 🚀",
            "",
            "<b>Quick Switch Commands:</b>",
            f"• <code>{cmd_pfx}aiset model flash</code>",
            f"• <code>{cmd_pfx}aiset model pro</code>",
            f"• <code>{cmd_pfx}aiset model 2.0</code>",
        ]
        return await m.handle_message("\n".join(lines))
    else:
        lines = [
            "🏠 <b>Ollama Local Models</b>",
            f"<i>Current active model:</i> <code>{html.escape(current)}</code>\n",
            "• <code>llama3.2</code> — <i>LLaMA 3.2 local</i> <b>[Default]</b>",
            "• <code>qwen2.5</code> — <i>Qwen 2.5 local</i>",
            "• <code>mistral</code> — <i>Mistral 7B local</i>",
            "",
            f"<b>Switch:</b> <code>{cmd_pfx}aiset model &lt;tag&gt;</code>",
        ]
        return await m.handle_message("\n".join(lines))


@Friday.register_on_cmd(
    ["aiset"],
    cmd_help={
        "help": "Configure AI settings. Subcommands: provider <name>, model <name|alias>, models (list models), sys <prompt>, apikey <key>",
        "example": "aiset model fast\n• .aiset models\n• .aiset provider groq\n• .aiset sys You are a witty companion.",
    },
    requires_input=False,
)
@log_errors
async def ai_set_cmd(c: Client, m: Message):
    raw = (m.user_input or "").strip()
    chat_id = m.chat_id or m.sender_id
    cfg = await _get_cfg(chat_id)
    provider = cfg.get("provider", "groq")

    cmd_pfx = getattr(Friday, "user_command_handler", ".") or "."
    if isinstance(cmd_pfx, (list, tuple)):
        cmd_pfx = cmd_pfx[0]

    if not raw or raw.lower() in ("models", "list", "model list", "models list", "list models"):
        return await _show_available_models(m, provider, cfg.get("model"))

    parts = raw.split(None, 1)
    sub = parts[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("models", "list"):
        return await _show_available_models(m, provider, cfg.get("model"))

    if not value:
        if sub == "model":
            return await _show_available_models(m, provider, cfg.get("model"))
        return await m.handle_message(
            "⚙️ <b>AI Settings</b>\n\n"
            "<b>Usage:</b>\n"
            f"• <code>{cmd_pfx}aiset models</code> — <i>Show active models list</i>\n"
            f"• <code>{cmd_pfx}aiset model fast|smart|120b|qwen|&lt;name&gt;</code>\n"
            f"• <code>{cmd_pfx}aiset provider groq|gemini|ollama</code>\n"
            f"• <code>{cmd_pfx}aiset sys &lt;custom personality prompt&gt;</code>\n"
            f"• <code>{cmd_pfx}aiset apikey &lt;key&gt;</code>"
        )

    if sub == "provider":
        if value not in ("groq", "gemini", "ollama"):
            return await m.handle_message(
                "❌ Unknown provider. Choose: <code>groq</code>, <code>gemini</code>, <code>ollama</code>"
            )
        default_model = _DEFAULT_MODELS.get(value)
        await _set_cfg(chat_id, provider=value, model=default_model)
        label = _PROVIDER_DISPLAY.get(value, value)
        return await m.handle_message(
            f"✅ AI provider set to <b>{label}</b>\n<i>Default model:</i> <code>{default_model}</code>"
        )

    if sub == "model":
        resolved = _resolve_model(provider, value)
        await _set_cfg(chat_id, model=resolved)
        alias_note = (
            f" <i>(alias for <code>{html.escape(value)}</code>)</i>" if resolved.lower() != value.lower() else ""
        )
        return await m.handle_message(f"✅ Model set to <code>{html.escape(resolved)}</code>{alias_note}")

    if sub in ("sys", "system"):
        await _set_cfg(chat_id, system=value)
        return await m.handle_message(f"✅ System prompt set:\n<i>{html.escape(value[:200])}</i>")

    if sub == "apikey":
        key_map = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
        env_key = key_map.get(provider)
        if not env_key:
            return await m.handle_message("❌ API keys are not needed for Ollama (local).")
        await Friday.config.set_env(env_key, value)
        return await m.handle_message(f"✅ <b>{env_key}</b> saved to database.")

    await m.handle_message(f"❓ Unknown subcommand: <code>{html.escape(sub)}</code>")


@Friday.register_on_cmd(
    ["aisys"],
    cmd_help={
        "help": "Set a custom system/personality prompt for the AI in this chat.",
        "example": "aisys You are a sarcastic assistant who speaks only in riddles.",
    },
    requires_input=True,
)
@log_errors
async def ai_sys_cmd(c: Client, m: Message):
    system_prompt = (m.user_input or "").strip()
    chat_id = m.chat_id or m.sender_id
    await _set_cfg(chat_id, system=system_prompt)
    await m.handle_message(f"🧠 <b>System prompt set!</b>\n<i>{html.escape(system_prompt[:300])}</i>")


@Friday.register_on_cmd(
    ["aireset"],
    cmd_help={
        "help": "Clear AI conversation history for the current chat.",
        "example": "aireset",
    },
)
@log_errors
async def ai_reset_cmd(c: Client, m: Message):
    chat_id = m.chat_id or m.sender_id
    await _clear_history(chat_id)
    await m.handle_message("🗑️ <b>Conversation history cleared.</b> Fresh start!")


@Friday.register_on_cmd(
    ["aistatus"],
    cmd_help={
        "help": "Show current AI provider, model, system prompt, and database auto-chat configuration.",
        "example": "aistatus",
    },
)
@log_errors
async def ai_status_cmd(c: Client, m: Message):
    chat_id = m.chat_id or m.sender_id
    cfg = await _get_cfg(chat_id)
    history = await _get_history(chat_id)
    provider = cfg.get("provider", "groq")
    model = cfg.get("model") or _DEFAULT_MODELS.get(provider, "default")
    system = cfg.get("system") or "<i>Not set (using built-in default)</i>"
    label = _PROVIDER_DISPLAY.get(provider, provider)

    groq_key = "✅ Set" if await Friday.config.get_env("GROQ_API_KEY") else "❌ Missing"
    gemini_key = "✅ Set" if await Friday.config.get_env("GEMINI_API_KEY") else "❌ Missing"
    ollama_url = await Friday.config.get_env("OLLAMA_URL") or "http://localhost:11434"

    users, chats = await _get_autochat_list()
    autochat_status = (
        f"✅ {len(users)} user(s), {len(chats)} group(s) active in DB" if (users or chats) else "❌ Disabled"
    )

    turns = len(history) // 2
    text = (
        f"🤖 <b>AI Configuration</b>\n\n"
        f"• <b>Provider:</b> {label}\n"
        f"• <b>Model:</b> <code>{html.escape(model)}</code>\n"
        f"• <b>Auto-Chat:</b> {autochat_status}\n"
        f"• <b>History:</b> {turns} turn(s) in memory\n"
        f"• <b>System Prompt:</b> {system[:150] if isinstance(system, str) else system}\n\n"
        f"<b>API Keys:</b>\n"
        f"  — GROQ_API_KEY: {groq_key}\n"
        f"  — GEMINI_API_KEY: {gemini_key}\n"
        f"  — Ollama URL: <code>{html.escape(ollama_url)}</code>\n\n"
        f"<i>Use <code>.aiset</code> or <code>.aichat</code> to change these.</i>"
    )
    await m.handle_message(text)


@Friday.bot.on_inline_query(filters.regex(r"^ai\s+(.+)", flags=2))  # IGNORECASE
@log_errors
@iuser_check
async def ai_inline_handler(c, iq):
    import re

    match = re.match(r"^ai\s+(.+)", iq.text, re.IGNORECASE)
    if not match:
        return

    prompt = match.group(1).strip()
    sender_id = iq.sender_id
    reply = await _ask_ai(prompt, sender_id, one_shot=True)

    # Truncate for inline article preview
    preview = reply[:200] + "…" if len(reply) > 200 else reply

    buttons = [
        [
            custom.Button.inline("🔁 Regenerate", f"ai_regen#{prompt[:64]}".encode()),
            custom.Button.inline("❌ Close", b"close_help"),
        ]
    ]

    builder = iq.builder
    result = builder.article(
        title=f"AI: {prompt[:50]}",
        description=preview,
        text=f"<b>❓ {html.escape(prompt)}</b>\n\n{reply}",
        parse_mode="html",
        buttons=buttons,
    )
    await iq.answer([result], cache_time=10)


@Friday.bot.on_callback_query(filters.regex(r"^ai_regen#(.+)"))
@log_errors
@iuser_check
async def ai_regen_callback(c, cq):
    import re

    data = cq.data.decode() if isinstance(cq.data, bytes) else str(cq.data)
    match = re.match(r"^ai_regen#(.+)", data)
    if not match:
        return await cq.answer("❌ Could not extract prompt.", alert=True)

    prompt = match.group(1)
    await cq.answer("⏳ Regenerating…")
    reply = await _ask_ai(prompt, cq.sender_id, one_shot=True)

    buttons = [
        [
            custom.Button.inline("🔁 Regenerate", f"ai_regen#{prompt[:64]}".encode()),
            custom.Button.inline("❌ Close", b"close_help"),
        ]
    ]
    await cq.edit(
        f"<b>❓ {html.escape(prompt)}</b>\n\n{reply}",
        parse_mode="html",
        buttons=buttons,
    )
