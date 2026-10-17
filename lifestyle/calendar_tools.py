# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import calendar
import datetime
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


@Friday.register_on_cmd(
    ["cal", "calendar"],
    cmd_help={
        "help": "Display a monthly calendar. If no args provided, shows current month.",
        "example": "cal or cal 12 2026",
    },
)
async def show_calendar(c: Client, m: Message):
    now = datetime.datetime.now()
    month = now.month
    year = now.year

    if m.user_input:
        parts = m.user_input.strip().split()
        if len(parts) == 1 and parts[0].isdigit():
            val = int(parts[0])
            if 1 <= val <= 12:
                month = val
            elif val > 1000:
                year = val
        elif len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            month = max(1, min(12, int(parts[0])))
            year = int(parts[1])

    cal_text = calendar.month(year, month)
    msg = (
        f"📅 <b>Calendar:</b>\n"
        f"<code>{cal_text}</code>"
    )
    await m.handle_message(msg)


@Friday.register_on_cmd(
    ["calcdate", "datediff", "countdown"],
    cmd_help={
        "help": "Calculate time difference between today and a target date (YYYY-MM-DD), or between two dates.",
        "example": "calcdate 2027-01-01 or calcdate 2026-01-01 to 2026-12-31",
    },
    requires_input=True,
)
async def date_calculator(c: Client, m: Message):
    raw = m.user_input.strip()
    now = datetime.datetime.now()

    def parse_dt(s: str) -> datetime.date:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.datetime.strptime(s.strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError(f"Invalid date format: {s}. Use YYYY-MM-DD or DD/MM/YYYY.")

    try:
        if " to " in raw:
            parts = raw.split(" to ")
            d1 = parse_dt(parts[0])
            d2 = parse_dt(parts[1])
            diff = abs((d2 - d1).days)
            weeks = diff // 7
            rem_days = diff % 7
            report = (
                f"<b>🗓 Date Difference</b>\n"
                f"<b>• From:</b> <code>{d1}</code>\n"
                f"<b>• To:</b> <code>{d2}</code>\n"
                f"<b>• Total Days:</b> <code>{diff}</code> days ({weeks} weeks, {rem_days} days)"
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
            status = f"⏳ <b>{diff} days remaining</b> ({weeks} weeks and {rem_days} days) until <code>{target_date}</code>"
        else:
            abs_diff = abs(diff)
            weeks = abs_diff // 7
            rem_days = abs_diff % 7
            status = f"⌛ <b>{abs_diff} days ago</b> ({weeks} weeks and {rem_days} days) since <code>{target_date}</code>"

        weekday_name = calendar.day_name[target_date.weekday()]
        day_of_year = target_date.timetuple().tm_yday

        report = (
            f"<b>🗓 Date Inspection:</b> <code>{target_date}</code>\n"
            f"<b>• Day:</b> {weekday_name}\n"
            f"<b>• Day of Year:</b> {day_of_year}/365\n"
            f"<b>• Status:</b> {status}"
        )
        await m.handle_message(report)
    except Exception as e:
        await m.handle_message(f"❌ Error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["curtime", "worldtime"],
    cmd_help={
        "help": "Display current UTC time and local server time.",
        "example": "curtime",
    },
)
async def current_time(c: Client, m: Message):
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    local_now = datetime.datetime.now()

    report = (
        "<b>🕒 Current Time</b>\n\n"
        f"<b>• UTC:</b> <code>{utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n"
        f"<b>• Local Server:</b> <code>{local_now.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"<b>• Day:</b> {utc_now.strftime('%A')}\n"
        f"<b>• Week:</b> {utc_now.strftime('%W')}"
    )
    await m.handle_message(report)
