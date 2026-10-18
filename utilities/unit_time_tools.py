# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import time
import datetime
import urllib.parse
import httpx

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

# Conversion ratios relative to SI base units
LENGTH_FACTORS = {
    "m": 1.0,
    "km": 1000.0,
    "cm": 0.01,
    "mm": 0.001,
    "mi": 1609.344,
    "yd": 0.9144,
    "ft": 0.3048,
    "in": 0.0254,
}
MASS_FACTORS = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "lb": 0.45359237,
    "oz": 0.028349523125,
    "ton": 1000.0,
}
DATA_FACTORS = {
    "b": 1.0,
    "kb": 1024.0,
    "mb": 1024.0**2,
    "gb": 1024.0**3,
    "tb": 1024.0**4,
}
SPEED_FACTORS = {
    "ms": 1.0,
    "kmh": 1.0 / 3.6,
    "mph": 0.44704,
    "knot": 0.514444,
}


def _convert_units(val: float, from_u: str, to_u: str):
    f, t = from_u.lower(), to_u.lower()
    # Temperature
    if f in {"c", "celsius"} and t in {"f", "fahrenheit"}:
        return (val * 9 / 5) + 32, "°F"
    if f in {"f", "fahrenheit"} and t in {"c", "celsius"}:
        return (val - 32) * 5 / 9, "°C"
    if f in {"c", "celsius"} and t in {"k", "kelvin"}:
        return val + 273.15, "K"
    if f in {"k", "kelvin"} and t in {"c", "celsius"}:
        return val - 273.15, "°C"

    # Length
    if f in LENGTH_FACTORS and t in LENGTH_FACTORS:
        meters = val * LENGTH_FACTORS[f]
        return meters / LENGTH_FACTORS[t], t

    # Mass
    if f in MASS_FACTORS and t in MASS_FACTORS:
        kgs = val * MASS_FACTORS[f]
        return kgs / MASS_FACTORS[t], t

    # Data
    if f in DATA_FACTORS and t in DATA_FACTORS:
        bytes_ = val * DATA_FACTORS[f]
        return bytes_ / DATA_FACTORS[t], t

    # Speed
    if f in SPEED_FACTORS and t in SPEED_FACTORS:
        ms = val * SPEED_FACTORS[f]
        return ms / SPEED_FACTORS[t], t

    return None, None


@Friday.register_on_cmd(
    ["convert", "conv", "unit"],
    cmd_help={
        "help": "Convert units: length (km, mi, ft), mass (kg, lb, oz), temperature (c, f), data (mb, gb), and speed.",
        "example": "convert 50 kg lb\nconvert 100 kmh mph\nconvert 75 f c\nconvert 2.5 gb mb",
    },
    requires_input=True,
)
async def unit_convert_cmd(c: Client, m: Message):
    tokens = [t for t in m.user_input.strip().split() if t.lower() != "to"]
    if len(tokens) < 3:
        return await m.handle_message(
            "⚠️ <b>Usage:</b> <code>.convert &lt;value&gt; &lt;from_unit&gt; [to] &lt;to_unit&gt;</code>\n"
            "• Examples: <code>.convert 100 km to miles</code>, <code>.convert 50 kg lb</code>\n"
            "• Length: <code>km, mi, m, ft, in, yd</code>\n"
            "• Weight: <code>kg, lb, g, oz</code>\n"
            "• Temp: <code>c, f, k</code>\n"
            "• Data: <code>mb, gb, tb, kb</code>\n"
            "• Speed: <code>kmh, mph, ms, knot</code>"
        )

    try:
        val = float(tokens[0])
    except ValueError:
        return await m.handle_message("❌ Value must be a valid number.")

    from_u, to_u = tokens[1], tokens[2]
    res, unit_str = _convert_units(val, from_u, to_u)
    if res is None:
        return await m.handle_message(
            f"❌ Incompatible or unsupported units: <code>{from_u}</code> ➔ <code>{to_u}</code>."
        )

    report = f"📏 <b>Unit Conversion:</b>\n\n<b>{val:,.2f} {from_u.upper()}</b> = <b>{res:,.4f} {unit_str.upper()}</b>"
    await m.handle_message(report)


@Friday.register_on_cmd(
    ["time", "clock", "tz", "timezone"],
    cmd_help={
        "help": "Display current time for any world city or calculate time difference between two cities.",
        "example": "time Tokyo\ntime London\ntime diff New York Tokyo",
    },
    requires_input=True,
)
async def world_time_cmd(c: Client, m: Message):
    raw = m.user_input.strip()

    pfx = getattr(m, "prefix", ".") or "."
    if raw.lower().startswith("diff "):
        # Time difference mode
        cities = raw[5:].split()
        if len(cities) < 2:
            return await m.handle_message(f"⚠️ <b>Usage:</b> <code>{pfx}time diff &lt;City1&gt; &lt;City2&gt;</code>")
        city1, city2 = cities[0], cities[1]
        msg = await m.handle_message(f"⏱ Calculating timezone difference between <b>{city1}</b> and <b>{city2}</b>...")

        import zoneinfo

        async def _get_city_info(client, c_name):
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(c_name)}&count=1&language=en&format=json"
            resp = await client.get(geo_url)
            data = resp.json() if resp.status_code == 200 else {}
            res = data.get("results", [])
            return res[0] if res else None

        async with httpx.AsyncClient(timeout=10.0) as client:
            info1 = await _get_city_info(client, city1)
            info2 = await _get_city_info(client, city2)

        if not info1 or not info2:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            return await msg.edit_msg(
                f"⚠️ Could not resolve one of the locations (<b>{city1}</b> / <b>{city2}</b>).\n"
                f"🕒 UTC: <code>{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>"
            )

        tz1 = zoneinfo.ZoneInfo(info1.get("timezone", "UTC"))
        tz2 = zoneinfo.ZoneInfo(info2.get("timezone", "UTC"))
        now1 = datetime.datetime.now(tz1)
        now2 = datetime.datetime.now(tz2)
        offset1 = now1.utcoffset() or datetime.timedelta(0)
        offset2 = now2.utcoffset() or datetime.timedelta(0)
        diff_hours = (offset2 - offset1).total_seconds() / 3600

        ahead_str = (
            f"{abs(diff_hours):g} hours ahead"
            if diff_hours > 0
            else (f"{abs(diff_hours):g} hours behind" if diff_hours < 0 else "same time")
        )

        report = (
            f"🌐 <b>Time Difference Analysis:</b>\n\n"
            f"📍 <b>{info1.get('name', city1)} ({info1.get('timezone', 'UTC')}):</b> <code>{now1.strftime('%I:%M %p, %b %d')}</code>\n"
            f"📍 <b>{info2.get('name', city2)} ({info2.get('timezone', 'UTC')}):</b> <code>{now2.strftime('%I:%M %p, %b %d')}</code>\n\n"
            f"⏱ <b>Comparison:</b> {info2.get('name', city2)} is <b>{ahead_str}</b> of {info1.get('name', city1)}."
        )
        return await msg.edit_msg(report)

    city = raw
    msg = await m.handle_message(f"🕒 Fetching local time for <b>{city}</b>...")

    # Query timezone data via open-meteo geocoding
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(geo_url)
            data = resp.json() if resp.status_code == 200 else {}

        results = data.get("results", [])
        if not results:
            return await msg.edit_msg(f"🤷‍♂️ Location <code>{city}</code> not found.")

        target = results[0]
        name = target.get("name")
        country = target.get("country", "")
        tz_name = target.get("timezone", "UTC")

        # Fetch time in timezone
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.datetime.now(tz)
        fmt_time = now.strftime("%I:%M:%S %p")
        fmt_date = now.strftime("%A, %B %d, %Y")
        offset = now.strftime("%z")
        formatted_offset = f"UTC{offset[:3]}:{offset[3:]}"

        report = (
            f"🕒 <b>World Clock:</b> <code>{name}, {country}</code>\n\n"
            f"⏰ <b>Current Time:</b> <code>{fmt_time}</code>\n"
            f"📅 <b>Date:</b> <code>{fmt_date}</code>\n"
            f"🌐 <b>Timezone:</b> <code>{tz_name} ({formatted_offset})</code>"
        )
        await msg.edit_msg(report)

    except Exception as e:
        await msg.edit_msg(f"❌ Time lookup error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["timestamp", "epoch", "unixtime"],
    cmd_help={
        "help": "Display current Unix epoch timestamp or parse a given timestamp into UTC and local datetime.",
        "example": "timestamp\ntimestamp 1729145400",
    },
)
async def timestamp_cmd(c: Client, m: Message):
    raw = (m.user_input or "").strip()
    if not raw:
        now_ts = int(time.time())
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)
        return await m.handle_message(
            f"⏱ <b>Current Unix Epoch Timestamp:</b>\n\n"
            f"• <b>Timestamp:</b> <code>{now_ts}</code>\n"
            f"• <b>UTC Datetime:</b> <code>{now_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>"
        )

    try:
        ts = int(raw)
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        report = (
            f"⏱ <b>Timestamp Decoded:</b> <code>{ts}</code>\n\n"
            f"• <b>UTC Datetime:</b> <code>{dt.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n"
            f"• <b>Relative:</b> <code>{dt.strftime('%A, %B %d, %Y')}</code>"
        )
        await m.handle_message(report)
    except Exception:
        await m.handle_message("❌ Please provide a valid integer epoch timestamp.")
