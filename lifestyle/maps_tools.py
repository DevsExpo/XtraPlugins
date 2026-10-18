# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import math
import urllib.parse
from typing import Tuple, Optional
from telethon.tl.types import InputMediaGeoPoint, InputGeoPoint

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Calculate distance in km and miles between two points on Earth."""
    r_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    km = r_km * c
    miles = km * 0.621371
    return round(km, 2), round(miles, 2)


async def _geocode(query: str) -> Optional[dict]:
    """Geocode an address or landmark using Nominatim OpenStreetMap."""
    url = (
        f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&addressdetails=1&limit=1"
    )
    headers = {"User-Agent": "FridayUserbot/1.0 (https://github.com/FridaySoftware/Friday)"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0]
    return None


async def _download_static_map(lat: float, lon: float, zoom: int = 14) -> Optional[str]:
    """Download a static map preview image using OpenStreetMap / Carto or Yandex static tiles."""
    os.makedirs("temp/xtra_maps", exist_ok=True)
    out_file = f"temp/xtra_maps/map_{lat}_{lon}.png"

    # Option 1: Yandex Static Map API (High reliability, zero API key)
    yandex_url = f"https://static-maps.yandex.ru/1.x/?ll={lon},{lat}&z={zoom}&l=map&size=650,400&pt={lon},{lat},pm2rdm"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(yandex_url, headers={"User-Agent": "Mozilla/5.0"})
            if res.status_code == 200 and len(res.content) > 1000:
                with open(out_file, "wb") as f:
                    f.write(res.content)
                return out_file
    except Exception:
        pass

    return None


@Friday.register_on_cmd(
    ["map", "location", "osm", "whereis"],
    cmd_help={
        "help": "Search any location or landmark worldwide, receiving a high-res static map photo, coordinates, and navigation links.",
        "example": "map Eiffel Tower, Paris\nmap Tokyo Skytree -z 16 (custom zoom 3-18)",
    },
    requires_input=True,
)
async def map_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for maps.")

    raw = m.user_input.strip()
    zoom = 14
    if "-z" in raw:
        parts = raw.split("-z")
        raw = parts[0].strip()
        try:
            zoom = int(parts[1].strip().split()[0])
            zoom = max(3, min(18, zoom))
        except Exception:
            pass

    query = raw
    msg = await m.handle_message(f"📍 Locating <b>{query}</b> and rendering map preview...")

    try:
        data = await _geocode(query)
        if not data:
            return await msg.edit_msg(f"❌ Location not found: <code>{query}</code>")

        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        display_name = data.get("display_name", query)
        osm_type = data.get("type", "landmark").replace("_", " ").title()

        address_info = data.get("address", {})
        country = address_info.get("country", "")
        city = address_info.get("city") or address_info.get("town") or address_info.get("village", "")

        osm_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"
        gmaps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        earth_url = f"https://earth.google.com/web/search/{lat},{lon}"

        caption = (
            f"📍 <b>Location Found:</b> <code>{query}</code>\n\n"
            f"• <b>Full Address:</b> {display_name}\n"
            f"• <b>Type:</b> <code>{osm_type}</code>\n"
            f"• <b>Region:</b> {city + ', ' if city else ''}{country}\n"
            f"• <b>Coordinates:</b> <code>{lat:.5f}, {lon:.5f}</code>\n\n"
            f"🔗 <a href='{osm_url}'>OpenStreetMap</a> | <a href='{gmaps_url}'>Google Maps</a> | <a href='{earth_url}'>Google Earth</a>"
        )

        map_img = await _download_static_map(lat, lon, zoom=zoom)
        target_chat = m.chat_id or getattr(m.chat, "id", None)

        if map_img and os.path.exists(map_img):
            await c.send_file(
                target_chat,
                map_img,
                caption=caption,
                reply_to=m.id,
            )
            try:
                await msg.delete()

            except Exception:
                pass
            try:
                os.remove(map_img)
            except Exception:
                pass
        else:
            await msg.edit_msg(caption, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Map search error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["geopin", "locpin", "sendlocation"],
    cmd_help={
        "help": "Send an interactive Telegram native location pin for any address or landmark.",
        "example": "pin Taj Mahal, Agra\npin 48.8584 2.2945",
    },
    requires_input=True,
)
async def send_pin(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"📌 Resolving coordinates for <b>{query}</b>...")

    try:
        # Check if user entered numbers "lat lon"
        tokens = query.split()
        if len(tokens) == 2 and all(t.replace(".", "").replace("-", "").isdigit() for t in tokens):
            lat = float(tokens[0])
            lon = float(tokens[1])
        else:
            data = await _geocode(query)
            if not data:
                return await msg.edit_msg(f"❌ Location not found: <code>{query}</code>")
            lat = float(data.get("lat"))
            lon = float(data.get("lon"))

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            InputMediaGeoPoint(InputGeoPoint(lat=lat, long=lon)),
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to send pin: <code>{e}</code>")


@Friday.register_on_cmd(
    ["directions", "route", "nav"],
    cmd_help={
        "help": "Get driving navigation route, turn-by-turn steps, distance, and duration between two places.",
        "example": "directions New York | Boston\nroute London | Oxford",
    },
    requires_input=True,
)
async def route_directions(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    query = m.user_input.strip()
    if "|" not in query:
        return await m.handle_message(
            "⚠️ Please provide origin and destination separated by '|':\n<code>.directions Berlin | Munich</code>"
        )

    origin_str, dest_str = [x.strip() for x in query.split("|", 1)]
    msg = await m.handle_message(f"🚗 Calculating route from <b>{origin_str}</b> to <b>{dest_str}</b>...")

    try:
        orig = await _geocode(origin_str)
        dest = await _geocode(dest_str)

        if not orig:
            return await msg.edit_msg(f"❌ Origin location not found: <code>{origin_str}</code>")
        if not dest:
            return await msg.edit_msg(f"❌ Destination location not found: <code>{dest_str}</code>")

        lat1, lon1 = float(orig["lat"]), float(orig["lon"])
        lat2, lon2 = float(dest["lat"]), float(dest["lon"])

        # Query Open Source Routing Machine (OSRM)
        osrm_url = (
            f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false&steps=true"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(osrm_url)

        if res.status_code != 200 or not res.json().get("routes"):
            # Fallback to Haversine distance
            km, miles = _haversine_distance(lat1, lon1, lat2, lon2)
            return await msg.edit_msg(
                f"🚗 <b>Direct Geographic Distance:</b>\n\n"
                f"• <b>From:</b> {orig.get('display_name')}\n"
                f"• <b>To:</b> {dest.get('display_name')}\n\n"
                f"📏 <b>Straight-Line Distance:</b> <code>{km} km</code> ({miles} miles)\n"
                f"<i>(Driving route network path was unavailable between these points)</i>"
            )

        route = res.json()["routes"][0]
        dist_km = round(route.get("distance", 0) / 1000, 1)
        dist_miles = round(dist_km * 0.621371, 1)
        dur_secs = route.get("duration", 0)
        hours = int(dur_secs // 3600)
        mins = int((dur_secs % 3600) // 60)
        duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins} mins"

        # Turn-by-turn steps
        legs = route.get("legs", [{}])[0]
        steps = legs.get("steps", [])
        step_lines = []
        for i, s in enumerate(steps[:8], 1):
            maneuver = s.get("maneuver", {}).get("instruction") or s.get("name") or "Continue straight"
            step_dist = round(s.get("distance", 0) / 1000, 1)
            step_lines.append(f"  <b>{i}.</b> {maneuver} (<code>{step_dist} km</code>)")

        steps_block = "\n".join(step_lines) if step_lines else "Follow highway signage."

        gmaps_nav = (
            f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"
        )

        report = (
            f"🚗 <b>Driving Navigation Route:</b>\n\n"
            f"• <b>Origin:</b> {orig.get('display_name')[:40]}...\n"
            f"• <b>Destination:</b> {dest.get('display_name')[:40]}...\n\n"
            f"📏 <b>Road Distance:</b> <code>{dist_km} km</code> ({dist_miles} miles)\n"
            f"⏱️ <b>Estimated Duration:</b> <code>{duration_str}</code>\n\n"
            f"<b>Turn-by-Turn Preview:</b>\n{steps_block}\n\n"
            f"🔗 <a href='{gmaps_nav}'>Open Live Navigation in Google Maps</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Route calculation error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["distance", "dist"],
    cmd_help={
        "help": "Calculate geographic straight-line distance between two locations or cities.",
        "example": "distance London | Paris",
    },
    requires_input=True,
)
async def map_distance(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    query = m.user_input.strip()
    if "|" not in query:
        return await m.handle_message(
            "⚠️ Please provide two locations separated by '|':\n<code>.distance London | Paris</code>"
        )

    loc1_str, loc2_str = [x.strip() for x in query.split("|", 1)]
    msg = await m.handle_message(f"📏 Calculating distance between <b>{loc1_str}</b> and <b>{loc2_str}</b>...")

    try:
        data1 = await _geocode(loc1_str)
        data2 = await _geocode(loc2_str)

        if not data1:
            return await msg.edit_msg(f"❌ Location 1 not found: <code>{loc1_str}</code>")
        if not data2:
            return await msg.edit_msg(f"❌ Location 2 not found: <code>{loc2_str}</code>")

        lat1, lon1 = float(data1.get("lat")), float(data1.get("lon"))
        lat2, lon2 = float(data2.get("lat")), float(data2.get("lon"))

        km, miles = _haversine_distance(lat1, lon1, lat2, lon2)

        report = (
            f"📏 <b>Geographic Distance Calculation:</b>\n\n"
            f"• <b>Point A:</b> {data1.get('display_name')}\n"
            f"• <b>Point B:</b> {data2.get('display_name')}\n\n"
            f"<b>• Kilometers:</b> <code>{km} km</code>\n"
            f"<b>• Miles:</b> <code>{miles} miles</code>\n"
            f"<b>• Nautical Miles:</b> <code>{round(km * 0.539957, 2)} nmi</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Distance calculation error: <code>{e}</code>")
