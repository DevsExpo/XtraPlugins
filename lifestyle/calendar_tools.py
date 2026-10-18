# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import calendar
import contextlib
import datetime
import html
import logging
from typing import Dict, List, Optional

from telethon import Button
from telethon.errors.rpcerrorlist import MessageNotModifiedError

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from XtraPlugins.ui_tokens import CALENDAR, STATUS

logger = logging.getLogger("friday.calendar")

# ─── Dynamic Holidays & Festivals Integration ────────────────────────────────
try:
    import holidays

    HAS_HOLIDAYS = True
except ImportError:
    HAS_HOLIDAYS = False


def get_country_holidays(year: int, country: str = "IN") -> Dict[datetime.date, str]:
    """Dynamically compute official gazetted holidays for any given year and country."""
    if HAS_HOLIDAYS:
        try:
            return holidays.country_holidays(country.upper(), years=year)
        except Exception as e:
            logger.debug(f"Holidays lookup error: {e}")
    return {}


_USER_EVENTS: Dict[tuple, List[str]] = {}


def _get_holidays_for_date(dt: datetime.date, country: str = "IN") -> List[str]:
    """Retrieve holidays/observances dynamically for a specific date."""
    h_dict = get_country_holidays(dt.year, country)
    if dt in h_dict:
        name = h_dict[dt]
        return [name]
    return []


def _build_calendar_markup(year: int, month: int, selected_day: Optional[int] = None) -> List[List[Button]]:
    """Build a monthly Telegram inline keyboard grid."""
    today = datetime.date.today()
    month_name = calendar.month_name[month]

    # Row 0: Navigation [ « Prev ] [ Month Year ] [ Next » ]
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

    nav_row = [
        Button.inline("«", data=f"cal:nav:{prev_y}:{prev_m}"),
        Button.inline(f"{month_name} {year}", data="cal:noop"),
        Button.inline("»", data=f"cal:nav:{next_y}:{next_m}"),
    ]

    # Row 1: Weekday headers
    header_row = [
        Button.inline("Mo", data="cal:noop"),
        Button.inline("Tu", data="cal:noop"),
        Button.inline("We", data="cal:noop"),
        Button.inline("Th", data="cal:noop"),
        Button.inline("Fr", data="cal:noop"),
        Button.inline("Sa", data="cal:noop"),
        Button.inline("Su", data="cal:noop"),
    ]

    # Days rows
    cal = calendar.monthcalendar(year, month)
    days_rows = []

    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(Button.inline(" ", data="cal:noop"))
            else:
                is_today = today.year == year and today.month == month and today.day == day
                is_selected = selected_day == day

                label = str(day)
                if is_selected:
                    label = f"[{day}]"
                elif is_today:
                    label = f"•{day}•"

                row.append(Button.inline(label, data=f"cal:day:{year}:{month}:{day}"))
        days_rows.append(row)

    # Bottom action row: [Today] [Indian Holidays] [Close]
    action_row = [
        Button.inline("🎯 Today", data=f"cal:nav:{today.year}:{today.month}:{today.day}"),
        Button.inline("🇮🇳 Holidays", data=f"cal:hols:{year}"),
        Button.inline("✖ Close", data="cal:close"),
    ]

    return [nav_row, header_row] + days_rows + [action_row]


def _render_calendar_caption(year: int, month: int, day: Optional[int] = None, chat_id: Optional[int] = None) -> str:
    """Render the descriptive header text above the calendar grid."""
    today = datetime.date.today()
    month_name = calendar.month_name[month]

    if day is None:
        if today.year == year and today.month == month:
            day = today.day
        else:
            day = 1

    dt = datetime.date(year, month, day)
    day_name = calendar.day_name[dt.weekday()]
    day_of_year = dt.timetuple().tm_yday
    days_in_year = 366 if calendar.isleap(year) else 365
    days_left = days_in_year - day_of_year

    holidays = _get_holidays_for_date(dt)
    holiday_str = f"🎉 <b>Holiday / Festival:</b> <code>{', '.join(holidays)}</code>\n" if holidays else ""

    # Check custom user events
    user_ev_str = ""
    if chat_id:
        key = (chat_id, dt.strftime("%Y-%m-%d"))
        events = _USER_EVENTS.get(key, [])
        if events:
            ev_list = "\n".join(f"  • {html.escape(e)}" for e in events)
            user_ev_str = f"{CALENDAR.PIN} <b>Scheduled Events:</b>\n{ev_list}\n"

    is_today_tag = (
        f" {CALENDAR.TODAY} (Today)" if (today.year == year and today.month == month and today.day == day) else ""
    )

    caption = (
        f"{CALENDAR.ICON} <b>Smart Calendar — {month_name} {year}</b>\n\n"
        f"• <b>Selected:</b> <b>{day_name}, {day} {month_name} {year}</b>{is_today_tag}\n"
        f"• <b>Day of Year:</b> <code>{day_of_year} / {days_in_year}</code> ({days_left} days left)\n"
        f"• <b>Week Number:</b> <code>Week {dt.isocalendar()[1]}</code>\n"
        f"{holiday_str}"
        f"{user_ev_str}\n"
        f"<i>Tap any day button below to inspect details & holidays.</i>"
    )
    return caption


def _render_ascii_fallback(year: int, month: int, chat_id: Optional[int] = None, pfx: str = ".") -> str:
    """Generate a clean ASCII monospace calendar for non-inline chats."""
    month_cal = calendar.month(year, month)
    today = datetime.date.today()

    hols_in_month = []
    days_in_month = calendar.monthrange(year, month)[1]
    for d in range(1, days_in_month + 1):
        dt = datetime.date(year, month, d)
        h = _get_holidays_for_date(dt)
        if h:
            hols_in_month.append(f"• {d:02d} {calendar.month_abbr[month]}: {', '.join(h)}")

    hol_text = ""
    if hols_in_month:
        hol_text = f"\n\n{CALENDAR.PARTY} <b>Holidays This Month:</b>\n" + "\n".join(hols_in_month)

    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    nav_hints = (
        f"\n\n{STATUS.CLI} <b>CLI Navigation (Text Mode):</b>\n"
        f"• <b>Next Month:</b> <code>{pfx}cal {next_m} {next_y}</code>\n"
        f"• <b>Prev Month:</b> <code>{pfx}cal {prev_m} {prev_y}</code>\n"
        f"• <b>Official Holidays:</b> <code>{pfx}holidays {year}</code>\n"
        f"• <b>Save Event:</b> <code>{pfx}addevent YYYY-MM-DD &lt;title&gt;</code>"
    )

    return (
        f"{CALENDAR.ICON} <b>Calendar: {calendar.month_name[month]} {year}</b>\n\n"
        f"<pre>{month_cal}</pre>"
        f"• <i>Today is: {today.strftime('%A, %d %B %Y')}</i>"
        f"{hol_text}"
        f"{nav_hints}"
    )


@Friday.register_on_cmd(
    ["cal", "calendar"],
    cmd_help={
        "help": "Display a smart interactive calendar with day picker, Indian holiday markers, and event agendas.",
        "example": [
            "cal",
            "cal 12 (December of current year)",
            "cal 10 2026",
            "cal text (force ASCII text fallback mode)",
        ],
    },
)
@log_errors
async def show_calendar(c: Client, m: Message):
    now = datetime.datetime.now()
    month = now.month
    year = now.year
    force_text = False

    chat_id = m.chat_id or getattr(m.chat, "id", None)

    if m.user_input:
        parts = m.user_input.strip().split()
        if "text" in parts or "ascii" in parts:
            force_text = True
            parts = [p for p in parts if p not in ("text", "ascii")]

        if len(parts) == 1 and parts[0].isdigit():
            val = int(parts[0])
            if 1 <= val <= 12:
                month = val
            elif val > 1000:
                year = val
        elif len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            month = max(1, min(12, int(parts[0])))
            year = int(parts[1])

    # 1. Attempt interactive inline widget if not forced to text
    if not force_text:
        try:
            from Main.utils.inline_helper import send_inline_widget

            if await send_inline_widget(c, m, f"cal:{year}:{month}"):
                return
        except Exception:
            pass

    # 2. Text / CLI Fallback Mode
    pfx = getattr(m, "prefix", None) or getattr(Friday, "user_command_handler", ".") or "."
    await m.handle_message(_render_ascii_fallback(year, month, chat_id, pfx=pfx), parse_mode="html")


@Friday.register_on_cmd(
    ["holidays", "festivals"],
    cmd_help={
        "help": "List major Indian national and festival holidays for a given year.",
        "example": ["holidays", "holidays 2026", "holidays 2027"],
    },
)
@log_errors
async def list_holidays(c: Client, m: Message):
    country = "IN"
    if m.user_input:
        parts = m.user_input.strip().split()
        for p in parts:
            if p.isdigit():
                year = int(p)
            elif len(p) == 2 and p.isalpha():
                country = p.upper()

    h_dict = get_country_holidays(year, country)
    lines = [f"🎉 <b>Official Gazetted Holidays ({country} — {year})</b>\n"]

    if h_dict:
        for dt, name in sorted(h_dict.items()):
            lines.append(f"• <b>{dt.strftime('%d %b (%a)')}:</b> {name}")
    else:
        lines.append(f"<i>No holiday data available for {country} in {year}.</i>")

    lines.append("\n<i>Plan your schedule and celebrations ahead!</i>")
    await m.handle_message("\n".join(lines), parse_mode="html")


@Friday.register_on_cmd(
    ["addevent", "calremind"],
    cmd_help={
        "help": "Add a custom event or milestone to your personal calendar agenda.",
        "example": ["addevent 2026-10-25 Birthday Party", "addevent 2026-11-01 Project Deadline"],
    },
    requires_input=True,
)
@log_errors
async def add_event_cmd(c: Client, m: Message):
    pfx = getattr(m, "prefix", None) or getattr(Friday, "user_command_handler", ".") or "."
    parts = m.user_input.strip().split(None, 1)
    if len(parts) < 2:
        return await m.handle_message(f"❌ Usage: <code>{pfx}addevent YYYY-MM-DD &lt;event title&gt;</code>")

    date_str, title = parts
    try:
        dt = datetime.datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return await m.handle_message(
            "❌ Invalid date format. Please use <code>YYYY-MM-DD</code> (e.g. <code>2026-12-25</code>)."
        )

    chat_id = m.chat_id or getattr(m.chat, "id", None)
    key = (chat_id, dt.strftime("%Y-%m-%d"))
    _USER_EVENTS.setdefault(key, []).append(title.strip())

    await m.handle_message(
        f"✅ <b>Event Saved to Calendar!</b>\n\n"
        f"• <b>Date:</b> <code>{dt.strftime('%A, %d %B %Y')}</code>\n"
        f"• <b>Event:</b> {html.escape(title.strip())}\n\n"
        f"<i>Inspect it anytime using <code>{pfx}cal {dt.month} {dt.year}</code> or <code>{pfx}events</code></i>"
    )


@Friday.register_on_cmd(
    ["events", "myagenda"],
    cmd_help={
        "help": "List all your saved upcoming calendar events and milestones.",
        "example": ["events"],
    },
)
@log_errors
async def list_events_cmd(c: Client, m: Message):
    chat_id = m.chat_id or getattr(m.chat, "id", None)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    pfx = getattr(m, "prefix", ".") or "."

    found = []
    for (cid, dt_str), ev_list in sorted(_USER_EVENTS.items()):
        if cid == chat_id and dt_str >= today_str:
            for ev in ev_list:
                found.append((dt_str, ev))

    if not found:
        return await m.handle_message(
            f"ℹ️ You have no upcoming scheduled events. Add one with <code>{pfx}addevent YYYY-MM-DD &lt;title&gt;</code>."
        )

    lines = ["📌 <b>Upcoming Calendar Agenda:</b>\n"]
    for dt_str, ev in found[:15]:
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d").date()
        diff = (dt - datetime.date.today()).days
        tag = "Today!" if diff == 0 else (f"in {diff} days" if diff > 0 else "")
        lines.append(f"• <b>{dt.strftime('%d %b %Y (%a)')}:</b> {html.escape(ev)} (<i>{tag}</i>)")

    await m.handle_message("\n".join(lines), parse_mode="html")


@Friday.register_on_cmd(
    ["calcdate", "datediff", "countdown"],
    cmd_help={
        "help": "Calculate difference between two dates, or countdown from today.",
        "example": ["calcdate 2027-01-01", "calcdate 2026-01-01 to 2026-12-31"],
    },
    requires_input=True,
)
@log_errors
async def date_calculator(c: Client, m: Message):
    raw = m.user_input.strip()
    now = datetime.datetime.now()

    def parse_dt(s: str) -> datetime.date:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.datetime.strptime(s.strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError(f"Invalid date: {s}. Use YYYY-MM-DD or DD/MM/YYYY.")

    try:
        if " to " in raw:
            parts = raw.split(" to ")
            d1 = parse_dt(parts[0])
            d2 = parse_dt(parts[1])
            diff = abs((d2 - d1).days)
            weeks = diff // 7
            rem_days = diff % 7
            report = (
                f"🗓 <b>Date Difference</b>\n\n"
                f"• <b>From:</b> <code>{d1}</code>\n"
                f"• <b>To:</b> <code>{d2}</code>\n"
                f"• <b>Total:</b> <code>{diff}</code> days ({weeks} weeks, {rem_days} days)"
            )
            return await m.handle_message(report)

        target_date = parse_dt(raw)
        today = now.date()
        diff = (target_date - today).days

        if diff == 0:
            status = "🎉 <b>Today is the target date!</b>"
        elif diff > 0:
            weeks = diff // 7
            rem_days = diff % 7
            status = f"⏳ <b>{diff} days remaining</b> ({weeks}w {rem_days}d) until <code>{target_date}</code>"
        else:
            abs_diff = abs(diff)
            weeks = abs_diff // 7
            rem_days = abs_diff % 7
            status = f"⌛ <b>{abs_diff} days ago</b> ({weeks}w {rem_days}d) since <code>{target_date}</code>"

        weekday_name = calendar.day_name[target_date.weekday()]
        hols = _get_holidays_for_date(target_date)
        hol_str = f"\n• <b>Observance:</b> <code>{', '.join(hols)}</code>" if hols else ""

        report = f"🗓 <b>Target Date:</b> <code>{target_date}</code> ({weekday_name})\n• {status}{hol_str}"
        await m.handle_message(report)
    except Exception as e:
        await m.handle_message(f"❌ Error calculating date: <code>{e}</code>")


# ─── Assistant Bot Inline Query & Callback Handlers ──────────────────────────

if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_inline_query(pattern=r"^cal(?::(\d+))?(?::(\d+))?$")
    async def on_calendar_inline_query(event):
        match = event.pattern_match
        now = datetime.datetime.now()
        year = int(match.group(1)) if match.group(1) and match.group(1).isdigit() else now.year
        month = int(match.group(2)) if match.group(2) and match.group(2).isdigit() else now.month

        caption = _render_calendar_caption(year, month, now.day if (now.year == year and now.month == month) else 1)
        markup = _build_calendar_markup(year, month, now.day if (now.year == year and now.month == month) else 1)

        builder = event.builder
        result = builder.article(
            title=f"📅 Calendar: {calendar.month_name[month]} {year}",
            description="Interactive monthly calendar with day picker and official holidays",
            text=caption,
            buttons=markup,
            parse_mode="html",
        )
        await event.answer([result], cache_time=30)


if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_callback_query(pattern=r"^cal:(nav|day|hols|close|noop):?(\d+)?:?(\d+)?:?(\d+)?$")
    async def on_calendar_callback(event):
        data = event.data.decode("utf-8")
        parts = data.split(":")
        action = parts[1]

        if action == "noop":
            return await event.answer()

        if action == "close":
            await event.answer("Closed")
            with contextlib.suppress(Exception):
                await event.delete()
            return

        chat_id = event.chat_id

        if action == "hols":
            year = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else datetime.date.today().year
            h_dict = get_country_holidays(year, "IN")
            lines = [f"🇮🇳 <b>Official Gazetted Holidays ({year})</b>\n"]
            for dt, name in sorted(h_dict.items()):
                lines.append(f"• {dt.strftime('%d %b')}: {name}")
            if not h_dict:
                lines.append("<i>No holiday data found for this year.</i>")
            await event.answer("Holidays loaded", alert=False)
            back_btn = [[Button.inline("🔙 Back to Calendar", data=f"cal:nav:{year}:1")]]
            with contextlib.suppress(MessageNotModifiedError):
                await event.edit("\n".join(lines), buttons=back_btn, parse_mode="html")
            return

        year = int(parts[2])
        month = int(parts[3])
        day = int(parts[4]) if len(parts) > 4 and parts[4] and parts[4].isdigit() else None

        caption = _render_calendar_caption(year, month, day, chat_id)
        markup = _build_calendar_markup(year, month, day)

        await event.answer(f"{calendar.month_abbr[month]} {day or 1}, {year}", alert=False)
        with contextlib.suppress(MessageNotModifiedError):
            await event.edit(caption, buttons=markup, parse_mode="html")
