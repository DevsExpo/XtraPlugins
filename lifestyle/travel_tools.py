# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import urllib.parse
from typing import Optional, Dict, Any
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _format_running_days(days_bitmask: str) -> str:
    """Format '1111111' into readable running days."""
    active_days = []
    for i, bit in enumerate(days_bitmask[:7]):
        if bit == "1":
            active_days.append(DAY_NAMES[i])
    if len(active_days) == 7:
        return "Daily (All 7 Days)"
    return ", ".join(active_days) if active_days else "Not running"


@Friday.register_on_cmd(
    ["train", "trainstatus", "rail"],
    cmd_help={
        "help": "Search train schedule and live route details directly in Telegram.",
        "example": "train 12951 or train 12301",
    },
    requires_input=True,
)
async def train_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for train tools.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🚆 Fetching train details for <b>{query}</b>...")

    url = f"https://erail.in/rail/getTrains.aspx?TrainNo={urllib.parse.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)

        if res.status_code != 200 or "^" not in res.text:
            # Fallback direct tracking links if API does not return payload
            encoded = urllib.parse.quote_plus(query)
            live_tracking_url = f"https://www.railyatri.in/live-train-status/{encoded}"
            confirm_tkt_url = f"https://www.confirmtkt.com/train-running-status/{encoded}"
            report = (
                f"🚆 <b>Train Status Links:</b> <code>{query}</code>\n\n"
                f"<b>• Live Tracking:</b> <a href='{live_tracking_url}'>RailYatri Status</a>\n"
                f"<b>• Schedule:</b> <a href='{confirm_tkt_url}'>ConfirmTkt Status</a>"
            )
            return await msg.edit_msg(report, disable_web_page_preview=False)

        chunks = res.text.split("^")
        if len(chunks) < 2:
            return await msg.edit_msg(f"❌ Train <code>{query}</code> not found.")

        raw = chunks[1].split("~")
        train_no = raw[0]
        train_name = raw[1]
        src_name = raw[2]
        src_code = raw[3]
        dst_name = raw[4]
        dst_code = raw[5]
        dep_time = raw[10].replace(".", ":")
        arr_time = raw[11].replace(".", ":")
        duration = raw[12].replace(".", "h ") + "m"
        days_str = _format_running_days(raw[13])
        train_type = raw[27] if len(raw) > 27 else "Express"

        encoded = urllib.parse.quote_plus(train_no)
        live_link = f"https://www.railyatri.in/live-train-status/{encoded}"
        booking_link = f"https://www.confirmtkt.com/train-running-status/{encoded}"

        report = (
            f"🚆 <b>{train_name}</b> (<code>#{train_no}</code>)\n\n"
            f"<b>• From:</b> {src_name} (<code>{src_code}</code>)\n"
            f"<b>• To:</b> {dst_name} (<code>{dst_code}</code>)\n"
            f"<b>• Departure:</b> <code>{dep_time}</code>\n"
            f"<b>• Arrival:</b> <code>{arr_time}</code>\n"
            f"<b>• Duration:</b> <code>{duration}</code>\n"
            f"<b>• Running Days:</b> {days_str}\n"
            f"<b>• Type:</b> <code>{train_type}</code>\n\n"
            f"🔗 <a href='{live_link}'>Live Running GPS</a> | <a href='{booking_link}'>Station Schedule</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Error fetching train status: <code>{e}</code>")


@Friday.register_on_cmd(
    ["flight", "flightstatus", "plane"],
    cmd_help={
        "help": "Track route and status of a flight callsign/code directly in Telegram.",
        "example": "flight DLH400 or flight UAE202",
    },
    requires_input=True,
)
async def flight_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    callsign = m.user_input.strip().upper().replace(" ", "")
    msg = await m.handle_message(f"✈️ Tracking flight <b>{callsign}</b>...")

    api_url = f"https://opensky-network.org/api/routes?callsign={callsign}"
    fr24_url = f"https://www.flightradar24.com/data/flights/{callsign.lower()}"
    flightaware_url = f"https://www.flightaware.com/live/flight/{callsign}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})

        if res.status_code == 200:
            data = res.json()
            route = data.get("route", [])
            airline = data.get("operatorIata", "N/A")
            flight_num = data.get("flightNumber", callsign)
            origin = route[0] if len(route) > 0 else "Unknown"
            destination = route[1] if len(route) > 1 else "Unknown"
            updated = data.get("updateTime", "")[:10]

            report = (
                f"✈️ <b>Flight:</b> <code>{callsign}</code>\n\n"
                f"<b>• Operator / Airline:</b> <code>{airline}</code> (Flight <code>{flight_num}</code>)\n"
                f"<b>• Origin Airport (ICAO):</b> <code>{origin}</code>\n"
                f"<b>• Destination Airport (ICAO):</b> <code>{destination}</code>\n"
                f"<b>• Route Update:</b> <code>{updated}</code>\n\n"
                f"🔗 <a href='{fr24_url}'>FlightRadar24 Live Tracking</a> | <a href='{flightaware_url}'>FlightAware Route</a>"
            )
            return await msg.edit_msg(report, disable_web_page_preview=False)

        # Fallback to direct tracking links if route database is offline
        report = (
            f"✈️ <b>Flight Tracker:</b> <code>{callsign}</code>\n\n"
            f"<b>• Live Radar (FlightRadar24):</b> <a href='{fr24_url}'>View Aircraft Live</a>\n"
            f"<b>• Flight Route (FlightAware):</b> <a href='{flightaware_url}'>View Gate & Times</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Flight lookup error: <code>{e}</code>")
