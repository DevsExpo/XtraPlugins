# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Dict, Any

from telethon import Button
from telethon.errors.rpcerrorlist import MessageNotModifiedError

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from XtraPlugins.ui_tokens import POMODORO, STATUS

logger = logging.getLogger("friday.pomodoro")

# ─── State Management ────────────────────────────────────────────────────────

# Active pomodoro sessions keyed by chat_id:
# {
#   "task": asyncio.Task,
#   "msg_id": int,
#   "chat_id": int,
#   "state": "WORK" | "BREAK" | "LONG_BREAK" | "PAUSED",
#   "prev_state": str,
#   "work_min": int,
#   "break_min": int,
#   "long_break_min": int,
#   "round": int,
#   "max_rounds": int,
#   "duration_sec": int,
#   "elapsed_sec": int,
#   "start_epoch": float,
#   "pause_epoch": float,
#   "paused": bool,
#   "completed_sessions": int,
#   "total_focus_sec": int,
# }
_POMO_SESSIONS: Dict[int, Dict[str, Any]] = {}
_POMO_STATS: Dict[int, Dict[str, int]] = {}  # user_id -> {"sessions": N, "focus_min": M}


def _render_progress_bar(elapsed: int, total: int, length: int = 14) -> str:
    """Render a clean Unicode progress bar."""
    if total <= 0:
        return "░" * length
    ratio = min(1.0, max(0.0, elapsed / total))
    filled = int(round(ratio * length))
    pct = int(ratio * 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"<code>[{bar}]</code> {pct}%"


def _format_time(sec: int) -> str:
    m, s = divmod(max(0, sec), 60)
    return f"{m:02d}:{s:02d}"


def _build_pomo_text(session: Dict[str, Any], is_inline: bool = True, pfx: str = ".") -> str:
    state = session["state"]
    state_labels = {
        "WORK": f"{POMODORO.WORK} <b>Focus Mode (Work Session)</b>",
        "BREAK": f"{POMODORO.BREAK} <b>Short Break (Rest & Recharge)</b>",
        "LONG_BREAK": f"{POMODORO.LONG_BREAK} <b>Long Break (Great Job!)</b>",
        "PAUSED": f"{POMODORO.PAUSE} <b>Session Paused</b>",
    }
    label = state_labels.get(state, f"{POMODORO.TOMATO} <b>Pomodoro Timer</b>")

    total = session["duration_sec"]
    elapsed = session["elapsed_sec"]
    rem = max(0, total - elapsed)
    prog = _render_progress_bar(elapsed, total)

    round_str = f"{POMODORO.TOMATO} <b>Round {session['round']} of {session['max_rounds']}</b>"
    time_str = f"⏳ <b>{_format_time(rem)}</b> remaining (Total: {session['duration_sec'] // 60}m)"

    quote = "<i>Stay focused on one task at a time. Silence distractions.</i>"
    if state == "BREAK":
        quote = "<i>Step away from the screen, stretch, drink water!</i>"
    elif state == "LONG_BREAK":
        quote = "<i>Full cycle completed! Take a walk or relax.</i>"

    cli_hints = ""
    if not is_inline:
        cli_hints = (
            f"\n\n{STATUS.FLASH} <b>CLI Controls (Text Mode):</b>\n"
            f"• <b>Pause / Resume:</b> <code>{pfx}pomopause</code> | <code>{pfx}pomoresume</code>\n"
            f"• <b>Skip Session:</b> <code>{pfx}pomoskip</code>\n"
            f"• <b>Stop & Reset:</b> <code>{pfx}pomostop</code>\n"
            f"• <b>Check Stats:</b> <code>{pfx}pomostats</code>"
        )

    text = (
        f"{POMODORO.TOMATO} <b>Friday Pomodoro Focus Timer</b>\n\n"
        f"• <b>Status:</b> {label}\n"
        f"• <b>Progress:</b> {round_str}\n"
        f"• <b>Time:</b> {time_str}\n"
        f"• {prog}\n\n"
        f"{quote}"
        f"{cli_hints}"
    )
    return text


def _build_pomo_buttons(chat_id: int, is_paused: bool, state: str) -> list[list[Button]]:
    pause_btn = (
        Button.inline("▶ Resume", data=f"pomo:resume:{chat_id}")
        if is_paused
        else Button.inline("⏸ Pause", data=f"pomo:pause:{chat_id}")
    )
    skip_btn = (
        Button.inline("⏭ Skip to Break", data=f"pomo:skip:{chat_id}")
        if state == "WORK"
        else Button.inline("⏭ Skip to Work", data=f"pomo:skip:{chat_id}")
    )
    buttons = [
        [pause_btn, skip_btn],
        [
            Button.inline("🛑 Stop & Reset", data=f"pomo:stop:{chat_id}"),
            Button.inline("📊 My Stats", data=f"pomo:stats:{chat_id}"),
        ],
    ]
    return buttons


async def _pomodoro_loop(c: Client, chat_id: int):
    """Background coroutine that handles timer ticks, edits, and session transitions."""
    session = _POMO_SESSIONS.get(chat_id)
    if not session:
        return

    try:
        while True:
            await asyncio.sleep(5)
            session = _POMO_SESSIONS.get(chat_id)
            if not session:
                break

            if session["paused"]:
                continue

            session["elapsed_sec"] += 5
            if session["state"] == "WORK":
                session["total_focus_sec"] += 5

            msg_id = session.get("msg_id")

            # Check if current session phase finished
            if session["elapsed_sec"] >= session["duration_sec"]:
                # Transition phase
                if session["state"] == "WORK":
                    session["completed_sessions"] += 1
                    u_stat = _POMO_STATS.setdefault(chat_id, {"sessions": 0, "focus_min": 0})
                    u_stat["sessions"] += 1
                    u_stat["focus_min"] += session["work_min"]

                    if session["round"] >= session["max_rounds"]:
                        session["state"] = "LONG_BREAK"
                        session["duration_sec"] = session["long_break_min"] * 60
                        session["elapsed_sec"] = 0
                        session["round"] = 1
                        alert_msg = f"🔔 <b>DING!</b> Great job completing all {session['max_rounds']} rounds! Enjoy your {session['long_break_min']}m long break! 🏖"
                    else:
                        session["state"] = "BREAK"
                        session["duration_sec"] = session["break_min"] * 60
                        session["elapsed_sec"] = 0
                        alert_msg = f"🔔 <b>DING!</b> Focus session {session['round']} finished! Take a {session['break_min']}m break. ☕"
                else:
                    # Break completed, resume work
                    if session["state"] == "BREAK":
                        session["round"] += 1
                    session["state"] = "WORK"
                    session["duration_sec"] = session["work_min"] * 60
                    session["elapsed_sec"] = 0
                    alert_msg = f"🔔 <b>Break is over!</b> Time for Round {session['round']} focus session. Let's get to work! 🔥"

                # Send an audible ping alert
                try:
                    await c.send_message(chat_id, alert_msg)
                except Exception as e:
                    logger.debug(f"Pomo alert message failed: {e}")

            # Update the widget message
            if msg_id:
                try:
                    text = _build_pomo_text(session, pfx=session.get("pfx", "."))
                    btns = _build_pomo_buttons(chat_id, session["paused"], session["state"])
                    with contextlib.suppress(MessageNotModifiedError):
                        await c.edit_message(chat_id, msg_id, text, buttons=btns, parse_mode="html")
                except Exception as exc:
                    logger.debug(f"Pomo edit exception: {exc}")

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error(f"Pomodoro loop crashed: {exc}", exc_info=True)


# ─── Commands ────────────────────────────────────────────────────────────────


@Friday.register_on_cmd(
    ["pomodoro", "pomo"],
    cmd_help={
        "help": "Start a smart Pomodoro focus timer with interactive controls, round tracking, and sound alerts.",
        "example": [
            "pomo",
            "pomo 45 10 (45m work, 10m break)",
            "pomo 25 5 20 (25m work, 5m break, 20m long break)",
        ],
    },
)
@log_errors
async def pomodoro_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    if not chat_id:
        return await m.handle_message("❌ Cannot determine chat ID.")

    pfx = getattr(m, "prefix", None) or getattr(Friday, "user_command_handler", ".") or "."
    # Check if already running in this chat
    if chat_id in _POMO_SESSIONS:
        cur = _POMO_SESSIONS[chat_id]
        return await m.handle_message(
            f"⚠️ <b>Pomodoro timer is already active!</b>\n"
            f"• <b>Current state:</b> {cur['state']}\n"
            f"• <b>Remaining:</b> {_format_time(cur['duration_sec'] - cur['elapsed_sec'])}\n\n"
            f"<i>Use <code>{pfx}pomostop</code> to end it or tap buttons on the widget.</i>"
        )

    # Parse custom times
    args = (m.user_input or "").strip().split()
    work_min = 25
    break_min = 5
    long_break_min = 15
    max_rounds = 4

    try:
        if len(args) >= 1 and args[0].isdigit():
            work_min = max(1, min(120, int(args[0])))
        if len(args) >= 2 and args[1].isdigit():
            break_min = max(1, min(60, int(args[1])))
        if len(args) >= 3 and args[2].isdigit():
            long_break_min = max(1, min(90, int(args[2])))
    except Exception:
        pass

    session = {
        "chat_id": chat_id,
        "state": "WORK",
        "prev_state": "WORK",
        "work_min": work_min,
        "break_min": break_min,
        "long_break_min": long_break_min,
        "round": 1,
        "max_rounds": max_rounds,
        "duration_sec": work_min * 60,
        "elapsed_sec": 0,
        "start_epoch": time.time(),
        "pause_epoch": 0.0,
        "paused": False,
        "completed_sessions": 0,
        "total_focus_sec": 0,
        "pfx": pfx,
    }

    text = _build_pomo_text(session, pfx=pfx)
    buttons = _build_pomo_buttons(chat_id, False, "WORK")

    # Send interactive widget
    try:
        sent = await m.handle_message(text, buttons=buttons)
        msg_id = getattr(sent, "id", None)
    except Exception:
        sent = await m.handle_message(text)
        msg_id = getattr(sent, "id", None)

    session["msg_id"] = msg_id
    session["task"] = asyncio.create_task(_pomodoro_loop(c, chat_id))
    _POMO_SESSIONS[chat_id] = session


@Friday.register_on_cmd(
    ["pomostop", "stopomo", "pomoreset"],
    cmd_help={
        "help": "Stop and cancel the active Pomodoro session in this chat.",
        "example": ["pomostop"],
    },
)
@log_errors
async def pomostop_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    session = _POMO_SESSIONS.pop(chat_id, None)
    if not session:
        return await m.handle_message("ℹ️ No active Pomodoro timer found in this chat.")

    task = session.get("task")
    if task and not task.done():
        task.cancel()

    focus_mins = session["total_focus_sec"] // 60
    await m.handle_message(
        f"🛑 <b>Pomodoro Timer Stopped</b>\n\n"
        f"• <b>Completed Sessions:</b> <code>{session['completed_sessions']}</code>\n"
        f"• <b>Total Focus Time:</b> <code>{focus_mins} minutes</code>\n"
        f"<i>Great effort! Take a good rest now.</i>"
    )


@Friday.register_on_cmd(
    ["pomostats"],
    cmd_help={
        "help": "View your Pomodoro focus stats and completed sessions.",
        "example": ["pomostats"],
    },
)
@log_errors
async def pomostats_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    stat = _POMO_STATS.get(chat_id, {"sessions": 0, "focus_min": 0})
    sessions = stat["sessions"]
    minutes = stat["focus_min"]
    hours = round(minutes / 60, 1)

    cur = _POMO_SESSIONS.get(chat_id)
    cur_status = f"Active ({cur['state']})" if cur else "Idle"

    text = (
        f"📊 <b>Friday Pomodoro Productivity Statistics</b>\n\n"
        f"• <b>Current Timer:</b> <code>{cur_status}</code>\n"
        f"• <b>Sessions Completed:</b> <code>{sessions}</code> 🍅\n"
        f"• <b>Total Focused Time:</b> <code>{minutes} mins</code> ({hours} hrs)\n\n"
        f"<i>Pro tip: 4 pomodoros a day (100 min) equals over 600 hours of deep work a year!</i>"
    )
    await m.handle_message(text)


@Friday.register_on_cmd(
    ["pomopause"],
    cmd_help={
        "help": "Pause the active Pomodoro session in this chat.",
        "example": ["pomopause"],
    },
)
@log_errors
async def pomopause_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    session = _POMO_SESSIONS.get(chat_id)
    if not session:
        return await m.handle_message("ℹ️ No active Pomodoro timer to pause.")
    session["paused"] = True
    session["prev_state"] = session["state"]
    session["state"] = "PAUSED"
    await m.handle_message("⏸ <b>Pomodoro timer paused.</b> Use <code>.pomoresume</code> to continue.")


@Friday.register_on_cmd(
    ["pomoresume"],
    cmd_help={
        "help": "Resume a paused Pomodoro session.",
        "example": ["pomoresume"],
    },
)
@log_errors
async def pomoresume_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    session = _POMO_SESSIONS.get(chat_id)
    if not session:
        return await m.handle_message("ℹ️ No active Pomodoro timer to resume.")
    session["paused"] = False
    session["state"] = session.get("prev_state", "WORK")
    await m.handle_message("▶ <b>Pomodoro timer resumed!</b> Stay focused! 🔥")


@Friday.register_on_cmd(
    ["pomoskip"],
    cmd_help={
        "help": "Skip current Pomodoro work session or break.",
        "example": ["pomoskip"],
    },
)
@log_errors
async def pomoskip_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    session = _POMO_SESSIONS.get(chat_id)
    if not session:
        return await m.handle_message("ℹ️ No active Pomodoro timer to skip.")
    if session["state"] == "WORK":
        session["state"] = "BREAK"
        session["duration_sec"] = session["break_min"] * 60
        session["elapsed_sec"] = 0
        await m.handle_message(f"⏭ <b>Skipped to break!</b> Enjoy your {session['break_min']}m rest. ☕")
    else:
        session["round"] += 1
        session["state"] = "WORK"
        session["duration_sec"] = session["work_min"] * 60
        session["elapsed_sec"] = 0
        await m.handle_message(f"⏭ <b>Skipped to Round {session['round']}!</b> Focus mode activated! 🔥")


# ─── Assistant Bot Inline Query & Callback Handlers ──────────────────────────

if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_inline_query(pattern=r"^pomo(?::(\d+))?(?::(\d+))?$")
    async def on_pomo_inline_query(event):
        match = event.pattern_match
        work_min = int(match.group(1)) if match.group(1) and match.group(1).isdigit() else 25
        break_min = int(match.group(2)) if match.group(2) and match.group(2).isdigit() else 5
        chat_id = event.chat_id or 0

        mock_session = {
            "state": "WORK",
            "round": 1,
            "max_rounds": 4,
            "duration_sec": work_min * 60,
            "elapsed_sec": 0,
        }
        text = _build_pomo_text(mock_session, is_inline=True)
        buttons = _build_pomo_buttons(chat_id, False, "WORK")

        builder = event.builder
        result = builder.article(
            title="🍅 Friday Pomodoro Focus Timer",
            description=f"{work_min}m focus / {break_min}m break session",
            text=text,
            buttons=buttons,
            parse_mode="html",
        )
        await event.answer([result], cache_time=10)


@Friday.bot.on_callback_query(pattern=r"^pomo:([a-z_]+):(-?\d+)$")
async def on_pomo_callback(event):
    data = event.data.decode("utf-8")
    _, action, chat_id_str = data.split(":")
    chat_id = int(chat_id_str)

    session = _POMO_SESSIONS.get(chat_id)
    if not session and action != "stats":
        return await event.answer("⚠️ This Pomodoro session is no longer active.", alert=True)

    if action == "pause":
        if session:
            session["paused"] = True
            session["prev_state"] = session["state"]
            session["state"] = "PAUSED"
            await event.answer("⏸ Timer paused", alert=False)
            text = _build_pomo_text(session)
            btns = _build_pomo_buttons(chat_id, True, session["state"])
            with contextlib.suppress(MessageNotModifiedError):
                await event.edit(text, buttons=btns, parse_mode="html")

    elif action == "resume":
        if session:
            session["paused"] = False
            session["state"] = session.get("prev_state", "WORK")
            await event.answer("▶ Timer resumed!", alert=False)
            text = _build_pomo_text(session)
            btns = _build_pomo_buttons(chat_id, False, session["state"])
            with contextlib.suppress(MessageNotModifiedError):
                await event.edit(text, buttons=btns, parse_mode="html")

    elif action == "skip":
        if session:
            if session["state"] == "WORK":
                session["state"] = "BREAK"
                session["duration_sec"] = session["break_min"] * 60
                session["elapsed_sec"] = 0
                await event.answer("⏭ Skipped to break!", alert=False)
            else:
                session["round"] += 1
                session["state"] = "WORK"
                session["duration_sec"] = session["work_min"] * 60
                session["elapsed_sec"] = 0
                await event.answer(f"⏭ Skipped to Round {session['round']} work!", alert=False)

            text = _build_pomo_text(session)
            btns = _build_pomo_buttons(chat_id, session["paused"], session["state"])
            with contextlib.suppress(MessageNotModifiedError):
                await event.edit(text, buttons=btns, parse_mode="html")

    elif action == "stop":
        sess = _POMO_SESSIONS.pop(chat_id, None)
        if sess:
            task = sess.get("task")
            if task and not task.done():
                task.cancel()
        await event.answer("🛑 Timer stopped.", alert=False)
        with contextlib.suppress(MessageNotModifiedError):
            await event.edit("🛑 <b>Pomodoro timer stopped and reset.</b>", buttons=None, parse_mode="html")

    elif action == "stats":
        stat = _POMO_STATS.get(chat_id, {"sessions": 0, "focus_min": 0})
        await event.answer(
            f"🍅 Completed: {stat['sessions']} sessions ({stat['focus_min']} mins focus)",
            alert=True,
        )
