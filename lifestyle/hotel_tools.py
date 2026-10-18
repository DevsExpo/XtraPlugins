# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import contextlib
import html
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from telethon import Button
from telethon.errors.rpcerrorlist import MessageNotModifiedError

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from XtraPlugins.ui_tokens import HOTEL, STATUS

logger = logging.getLogger("friday.hotels")

# ─── Curated Destinations & Hotel Intelligence Database ─────────────────────
# Covers major Indian hubs, hill stations, heritage & beach spots + international

_DESTINATIONS_DB: Dict[str, Dict[str, Any]] = {
    "goa": {
        "city": "Goa, India 🏖",
        "best_season": "Nov to Feb (Peak: Dec-Jan)",
        "vibe": "Beach parties, Portuguese heritage, water sports, shacks & relaxed susegad.",
        "avg_tariffs": {"budget": "₹1,200 – ₹2,800", "mid": "₹3,500 – ₹7,500", "luxury": "₹12,000 – ₹35,000+"},
        "neighborhoods": "North (Baga, Anjuna, Candolim) for nightlife; South (Palolem, Benaulim, Cavelossim) for quiet luxury.",
        "stays": {
            "luxury": [
                {
                    "name": "Taj Exotica Resort & Spa",
                    "rating": "4.8★",
                    "price": "₹22,000+",
                    "amenities": "Private beach, 9-hole golf, Jiva Spa, sea-facing villas",
                },
                {
                    "name": "W Goa (Vagator)",
                    "rating": "4.6★",
                    "price": "₹18,500+",
                    "amenities": "Rock pool, vibrant DJ lounge, luxury cabanas",
                },
                {
                    "name": "The Leela Goa (Cavelossim)",
                    "rating": "4.7★",
                    "price": "₹24,000+",
                    "amenities": "Lagoon & river view, 12-hole golf, private beach access",
                },
            ],
            "mid": [
                {
                    "name": "Fairfield by Marriott Calangute",
                    "rating": "4.3★",
                    "price": "₹5,200",
                    "amenities": "Outdoor pool, buffet breakfast, fitness center",
                },
                {
                    "name": "Novotel Goa Candolim",
                    "rating": "4.2★",
                    "price": "₹6,000",
                    "amenities": "3 outdoor pools, family suites, shuttle service",
                },
                {
                    "name": "Lemon Tree Amarante Beach Resort",
                    "rating": "4.2★",
                    "price": "₹4,800",
                    "amenities": "Portuguese architecture, spa, close to beach",
                },
            ],
            "budget": [
                {
                    "name": "Zostel Goa (Morjim / Anjuna)",
                    "rating": "4.5★",
                    "price": "₹800 (Dorm) / ₹2,400 (Pvt)",
                    "amenities": "Coworking cafe, pool, vibrant backpacker community",
                },
                {
                    "name": "BloomSuites | Calangute",
                    "rating": "4.3★",
                    "price": "₹2,600",
                    "amenities": "Clean minimalist rooms, CloudBed, pool",
                },
            ],
        },
    },
    "mumbai": {
        "city": "Mumbai, Maharashtra 🏙",
        "best_season": "Oct to Mar (Pleasant coastal breezes)",
        "vibe": "Financial powerhouse, Bollywood, coastal promenades, Marine Drive & Colaba colonial charm.",
        "avg_tariffs": {"budget": "₹1,800 – ₹3,500", "mid": "₹5,500 – ₹11,000", "luxury": "₹16,000 – ₹45,000+"},
        "neighborhoods": "Colaba / Fort for heritage; Bandra / Juhu for trendy nightlife; BKC / Airport for business.",
        "stays": {
            "luxury": [
                {
                    "name": "The Taj Mahal Palace (Colaba)",
                    "rating": "4.9★",
                    "price": "₹28,000+",
                    "amenities": "Historic 1903 icon, Gateway view, luxury butler service",
                },
                {
                    "name": "The Oberoi, Nariman Point",
                    "rating": "4.8★",
                    "price": "₹22,000+",
                    "amenities": "Unobstructed Arabian Sea & Queens Necklace views",
                },
                {
                    "name": "The St. Regis Mumbai (Lower Parel)",
                    "rating": "4.7★",
                    "price": "₹16,500+",
                    "amenities": "High-rise infinity pool, Palladium mall direct access",
                },
            ],
            "mid": [
                {
                    "name": "Trident Nariman Point",
                    "rating": "4.6★",
                    "price": "₹10,500",
                    "amenities": "Sea view rooms, 24/7 business center, spa",
                },
                {
                    "name": "Radisson Mumbai Andheri MIDC",
                    "rating": "4.2★",
                    "price": "₹6,200",
                    "amenities": "Near airport, rooftop bar, modern executive suites",
                },
                {
                    "name": "Bloom Hotel - Juhu",
                    "rating": "4.3★",
                    "price": "₹4,800",
                    "amenities": "Close to Juhu beach, high-speed Wi-Fi, sleek design",
                },
            ],
            "budget": [
                {
                    "name": "Abode Bombay (Colaba)",
                    "rating": "4.6★",
                    "price": "₹3,800",
                    "amenities": "Boutique heritage stay, artisan breakfast, vintage decor",
                },
                {
                    "name": "Zostel Mumbai (Andheri)",
                    "rating": "4.4★",
                    "price": "₹999 (Dorm) / ₹2,800 (Pvt)",
                    "amenities": "Rooftop terrace, cafe, co-working desks",
                },
            ],
        },
    },
    "delhi": {
        "city": "New Delhi / NCR 🏛",
        "best_season": "Oct to Mar (Crisp winter weather)",
        "vibe": "Mughal monuments, power corridors, culinary paradise (Chandni Chowk), wide boulevards.",
        "avg_tariffs": {"budget": "₹1,200 – ₹2,500", "mid": "₹4,000 – ₹8,500", "luxury": "₹14,000 – ₹38,000+"},
        "neighborhoods": "Aerocity for world-class transit stays; CP / Central for city sights; South Delhi (Hauz Khas) for cafes.",
        "stays": {
            "luxury": [
                {
                    "name": "The Imperial New Delhi (Janpath)",
                    "rating": "4.8★",
                    "price": "₹21,000+",
                    "amenities": "Colonial museum-style hotel, 24-acre gardens, award-winning spa",
                },
                {
                    "name": "The Leela Palace New Delhi (Chanakyapuri)",
                    "rating": "4.9★",
                    "price": "₹25,000+",
                    "amenities": "Rooftop infinity pool, grand royal suites, MEGU dining",
                },
                {
                    "name": "Andaz Delhi by Hyatt (Aerocity)",
                    "rating": "4.7★",
                    "price": "₹13,500+",
                    "amenities": "Spacious artist-curated rooms, gin bar, quick T3 airport access",
                },
            ],
            "mid": [
                {
                    "name": "The Lalit New Delhi (Connaught Place)",
                    "rating": "4.4★",
                    "price": "₹7,200",
                    "amenities": "Central CP location, art gallery, Kitty Su club",
                },
                {
                    "name": "Lemon Tree Premier Delhi Airport",
                    "rating": "4.2★",
                    "price": "₹5,500",
                    "amenities": "24/7 dining, airport shuttle, outdoor pool",
                },
            ],
            "budget": [
                {
                    "name": "Bloomrooms @ Janpath",
                    "rating": "4.4★",
                    "price": "₹3,200",
                    "amenities": "Signature bright yellow decor, spotless linen, near CP metro",
                },
                {
                    "name": "Zostel Delhi (Pahar Ganj)",
                    "rating": "4.3★",
                    "price": "₹750 (Dorm) / ₹2,200 (Pvt)",
                    "amenities": "Near New Delhi Railway Station, social terrace, tour assistance",
                },
            ],
        },
    },
    "jaipur": {
        "city": "Jaipur, Rajasthan (Pink City) 👑",
        "best_season": "Oct to Mar",
        "vibe": "Royal palaces, majestic hill forts (Amer, Nahargarh), colorful bazaars & royal Rajasthani thalis.",
        "avg_tariffs": {"budget": "₹1,000 – ₹2,200", "mid": "₹3,500 – ₹7,000", "luxury": "₹15,000 – ₹60,000+"},
        "neighborhoods": "Old City (Pink City) for markets; C-Scheme / Civil Lines for posh dining; Amer Road for palace vibes.",
        "stays": {
            "luxury": [
                {
                    "name": "Rambagh Palace (Taj)",
                    "rating": "4.9★",
                    "price": "₹45,000+",
                    "amenities": "Former Maharaja residence, sprawling gardens, vintage peacock lawns",
                },
                {
                    "name": "The Oberoi Rajvilas",
                    "rating": "4.9★",
                    "price": "₹38,000+",
                    "amenities": "Luxury tented villas with private plunge pools, 32-acre oasis",
                },
                {
                    "name": "Samode Haveli",
                    "rating": "4.7★",
                    "price": "₹16,000+",
                    "amenities": "Authentic 175-year-old painted haveli, quiet courtyard pool",
                },
            ],
            "mid": [
                {
                    "name": "ITC Rajputana, A Luxury Collection",
                    "rating": "4.5★",
                    "price": "₹7,500",
                    "amenities": "Traditional red brick architecture, royal dining",
                },
                {
                    "name": "Alsisar Haveli",
                    "rating": "4.4★",
                    "price": "₹5,200",
                    "amenities": "Heritage decor, vintage frescoes, garden pool",
                },
            ],
            "budget": [
                {
                    "name": "Zostel Jaipur",
                    "rating": "4.6★",
                    "price": "₹700 (Dorm) / ₹2,100 (Pvt)",
                    "amenities": "Rooftop lounge overlooking Hawa Mahal, group fort walks",
                },
                {
                    "name": "Umaid Bhawan - Heritage Style Hotel",
                    "rating": "4.4★",
                    "price": "₹2,600",
                    "amenities": "Intricate jharokhas, carved balconies, pool",
                },
            ],
        },
    },
    "bengaluru": {
        "city": "Bengaluru (Bangalore), Karnataka 💻",
        "best_season": "Year-round (Pleasant sub-tropical climate)",
        "vibe": "Silicon Valley of India, microbreweries, lush Cubbon Park, high-tech hubs & indie cafes.",
        "avg_tariffs": {"budget": "₹1,200 – ₹2,500", "mid": "₹4,200 – ₹8,500", "luxury": "₹12,000 – ₹28,000+"},
        "neighborhoods": "MG Road / Indiranagar for pubs & food; Whitefield / Electronic City for IT campuses; Koramangala for startups.",
        "stays": {
            "luxury": [
                {
                    "name": "The Leela Palace Bengaluru (Old Airport Rd)",
                    "rating": "4.9★",
                    "price": "₹18,500+",
                    "amenities": "Mysore Royal Palace design, 7 acres of manicured gardens",
                },
                {
                    "name": "The Ritz-Carlton, Bangalore (Residency Rd)",
                    "rating": "4.7★",
                    "price": "₹15,000+",
                    "amenities": "Rooftop bar 'Bang', marble bathrooms, luxury wellness spa",
                },
                {
                    "name": "Taj West End (Race Course Rd)",
                    "rating": "4.8★",
                    "price": "₹16,000+",
                    "amenities": "Historic 20-acre heritage hotel, 125-year-old banyan tree",
                },
            ],
            "mid": [
                {
                    "name": "Radisson Blu Atria Bengaluru",
                    "rating": "4.4★",
                    "price": "₹6,000",
                    "amenities": "Near Vidhana Soudha, executive lounge, pool",
                },
                {
                    "name": "Lemon Tree Premier, Ulsoor Lake",
                    "rating": "4.2★",
                    "price": "₹4,500",
                    "amenities": "Lake view rooms, cafe, fitness room",
                },
            ],
            "budget": [
                {
                    "name": "Bloom Hotel - Indiranagar",
                    "rating": "4.5★",
                    "price": "₹2,800",
                    "amenities": "Prime 100ft road location, silent rooms, fast Wi-Fi",
                },
                {
                    "name": "Zostel Bangalore (Indiranagar)",
                    "rating": "4.4★",
                    "price": "₹850 (Dorm) / ₹2,400 (Pvt)",
                    "amenities": "Coworking spaces, games room, vibrant events",
                },
            ],
        },
    },
    "manali": {
        "city": "Manali, Himachal Pradesh 🏔",
        "best_season": "Oct to Feb (Snow/Winter sports) or Apr to Jun (Summer escape)",
        "vibe": "Snow peaks, Solang Valley adventure, Rohtang Pass, Old Manali hippie cafes & pine forests.",
        "avg_tariffs": {"budget": "₹800 – ₹2,000", "mid": "₹3,000 – ₹6,500", "luxury": "₹9,000 – ₹25,000+"},
        "neighborhoods": "Old Manali for wooden cottages & live music; Vashisht for hot springs; Naggar for quiet nature.",
        "stays": {
            "luxury": [
                {
                    "name": "The Himalayan (Luxury Castle Resort)",
                    "rating": "4.7★",
                    "price": "₹14,500+",
                    "amenities": "Gothic castle architecture, orchard cottages, heated pool",
                },
                {
                    "name": "Span Resort and Spa (Kullu-Manali Hwy)",
                    "rating": "4.6★",
                    "price": "₹18,000+",
                    "amenities": "Beas riverbank frontage, helipad, luxury cedar chalets",
                },
            ],
            "mid": [
                {
                    "name": "Larisa Resort Manali",
                    "rating": "4.5★",
                    "price": "₹7,200",
                    "amenities": "Apple orchards, private fireplaces, organic dining",
                },
                {
                    "name": "Apple Country Resort",
                    "rating": "4.2★",
                    "price": "₹4,200",
                    "amenities": "Panoramic snow view, mountain spa, disco",
                },
            ],
            "budget": [
                {
                    "name": "Zostel Manali (Old Manali)",
                    "rating": "4.6★",
                    "price": "₹650 (Dorm) / ₹2,200 (Pvt)",
                    "amenities": "River views, bonfire nights, backpacker community",
                },
                {
                    "name": "The Hosteller Manali",
                    "rating": "4.4★",
                    "price": "₹600 (Dorm) / ₹1,900 (Pvt)",
                    "amenities": "High-speed Wi-Fi, mountain decks, cafe",
                },
            ],
        },
    },
}


def _get_booking_links(city_name: str) -> str:
    """Generate direct booking search links for major platforms."""
    enc = urllib.parse.quote_plus(city_name)
    links = [
        f'• <a href="https://www.makemytrip.com/hotels/{enc}-hotels.html">MakeMyTrip India</a>',
        f'• <a href="https://www.booking.com/searchresults.html?ss={enc}">Booking.com</a>',
        f'• <a href="https://www.agoda.com/search?text={enc}">Agoda Deals</a>',
        f'• <a href="https://www.google.com/travel/hotels/{enc}">Google Hotels Compare</a>',
    ]
    return "\n".join(links)


def _render_destination_summary(
    dest_data: Dict[str, Any],
    tier_filter: Optional[str] = None,
    is_inline: bool = True,
    city_key: str = "goa",
    pfx: str = ".",
) -> str:
    city = dest_data["city"]
    vibe = dest_data["vibe"]
    season = dest_data["best_season"]
    neighborhoods = dest_data["neighborhoods"]
    tariffs = dest_data["avg_tariffs"]

    stays = dest_data["stays"]

    lines = [
        f"{HOTEL.ICON} <b>Hotel & Stay Intelligence — {city}</b>\n",
        f"• <b>Best Season:</b> <i>{season}</i>",
        f"• <b>Vibe & Profile:</b> {vibe}",
        f"• <b>Locality Guide:</b> {neighborhoods}",
        f"• <b>Nightly Tariffs (Avg):</b> {HOTEL.BUDGET} Budget: <code>{tariffs['budget']}</code> | {HOTEL.MID} Mid: <code>{tariffs['mid']}</code> | {HOTEL.LUXURY} Luxury: <code>{tariffs['luxury']}</code>\n",
    ]

    tiers_to_show = [tier_filter] if (tier_filter and tier_filter in stays) else ["luxury", "mid", "budget"]

    for tier in tiers_to_show:
        tier_names = {
            "luxury": f"{HOTEL.LUXURY} Luxury & 5-Star Icons",
            "mid": f"{HOTEL.MID} Premium Mid-Range & Boutique",
            "budget": f"{HOTEL.BUDGET} Best Value & Backpacker Stays",
        }
        lines.append(f"<b>--- {tier_names.get(tier, tier.title())} ---</b>")
        for s in stays.get(tier, []):
            lines.append(
                f"• <b>{html.escape(s['name'])}</b> ({s['rating']})\n"
                f"  Tariff: <code>{s['price']}</code>/night\n"
                f"  <i>Highlights: {html.escape(s['amenities'])}</i>"
            )
        lines.append("")

    lines.append(f"{HOTEL.LINK} <b>Live Rates & Instant Booking:</b>")
    lines.append(_get_booking_links(city.split(",")[0]))

    if not is_inline:
        lines.append(f"\n{STATUS.CLI} <b>CLI Navigation (Text Mode):</b>")
        lines.append(
            f"• <b>Filter by Tier:</b> <code>{pfx}hotel {city_key} luxury</code> | <code>{pfx}hotel {city_key} mid</code> | <code>{pfx}hotel {city_key} budget</code>"
        )
        lines.append(f"• <b>Compare Stays:</b> <code>{pfx}hotelcompare {city_key} goa</code>")
        lines.append(
            f"• <b>Popular Destinations:</b> <code>{pfx}hotel goa</code> | <code>{pfx}hotel mumbai</code> | <code>{pfx}hotel jaipur</code> | <code>{pfx}hotel delhi</code> | <code>{pfx}hotel manali</code> | <code>{pfx}hotel bangalore</code>"
        )

    return "\n".join(lines)


def _render_generic_city(city: str, pfx: str = ".") -> str:
    """Fallback generator for any global or unlisted city."""
    lines = [
        f"🏨 <b>Hotel & Stay Discovery — {html.escape(city.title())}</b>\n",
        f"• <b>Destination:</b> <code>{html.escape(city.title())}</code>",
        "• <b>Guidance:</b> Explore verified properties, traveler reviews, and seasonal discount tariffs across top aggregators.\n",
        "🔗 <b>Compare Live Prices & Book Direct:</b>",
        _get_booking_links(city),
        f"\n<i>Tip: For curated breakdowns, try top destinations like <code>{pfx}hotel goa</code>, <code>{pfx}hotel mumbai</code>, <code>{pfx}hotel jaipur</code>, <code>{pfx}hotel delhi</code>, <code>{pfx}hotel manali</code>, <code>{pfx}hotel bangalore</code></i>",
    ]
    return "\n".join(lines)


def _build_hotel_buttons(city_key: str) -> List[List[Button]]:
    if city_key not in _DESTINATIONS_DB:
        return []
    return [
        [
            Button.inline("💎 Luxury Stays", data=f"htl:f:{city_key}:luxury"),
            Button.inline("🏨 Mid-Range", data=f"htl:f:{city_key}:mid"),
            Button.inline("🎒 Budget / Hostels", data=f"htl:f:{city_key}:budget"),
        ],
        [
            Button.inline("🔄 All Tiers View", data=f"htl:f:{city_key}:all"),
        ],
    ]


@Friday.register_on_cmd(
    ["hotel", "hotels", "stay"],
    cmd_help={
        "help": "Smart hotel, resort, and stay finder (focused on India and flexible globally) with tariffs, amenities, and booking links.",
        "example": [
            "hotel goa",
            "hotel mumbai luxury",
            "hotel jaipur budget",
            "hotel manali",
            "hotel -text goa (force text mode)",
        ],
    },
)
@log_errors
async def hotel_cmd(c: Client, m: Message):
    raw_input = (m.user_input or "goa").strip()
    force_text = "-text" in raw_input or "-cli" in raw_input
    clean_input = raw_input.replace("-text", "").replace("-cli", "").strip()

    args = clean_input.split() if clean_input else ["goa"]
    city_raw = args[0].lower() if args else "goa"
    tier_filter = args[1].lower() if len(args) > 1 and args[1].lower() in ("luxury", "mid", "budget") else None

    # Normalization
    aliases = {
        "bangalore": "bengaluru",
        "bombay": "mumbai",
        "newdelhi": "delhi",
        "pinkcity": "jaipur",
    }
    city_key = aliases.get(city_raw, city_raw)

    # 1. Attempt interactive inline widget if not forced to text
    if not force_text and city_key in _DESTINATIONS_DB:
        try:
            from Main.utils.inline_helper import send_inline_widget

            if await send_inline_widget(c, m, f"hotel:{city_key}"):
                return
        except Exception:
            pass

    # 2. Text / CLI Fallback Mode
    pfx = getattr(m, "prefix", None) or getattr(Friday, "user_command_handler", ".") or "."
    if city_key in _DESTINATIONS_DB:
        data = _DESTINATIONS_DB[city_key]
        text = _render_destination_summary(data, tier_filter, is_inline=False, city_key=city_key, pfx=pfx)
        await m.handle_message(text, parse_mode="html", link_preview=False)
    else:
        text = _render_generic_city(city_raw, pfx=pfx)
        await m.handle_message(text, parse_mode="html", link_preview=False)


@Friday.register_on_cmd(
    ["hotelcompare", "staycompare"],
    cmd_help={
        "help": "Compare two travel destinations side-by-side for hotel tariffs, vibe, and stay styles.",
        "example": ["hotelcompare goa manali", "hotelcompare mumbai jaipur"],
    },
    requires_input=True,
)
@log_errors
async def hotel_compare_cmd(c: Client, m: Message):
    pfx = getattr(m, "prefix", None) or getattr(Friday, "user_command_handler", ".") or "."
    parts = m.user_input.strip().split()
    if len(parts) < 2:
        return await m.handle_message(
            f"❌ Usage: <code>{pfx}hotelcompare &lt;city1&gt; &lt;city2&gt;</code> (e.g. <code>{pfx}hotelcompare goa manali</code>)"
        )

    c1 = parts[0].lower()
    c2 = parts[1].lower()

    d1 = _DESTINATIONS_DB.get(c1)
    d2 = _DESTINATIONS_DB.get(c2)

    if not d1 or not d2:
        return await m.handle_message(
            f"❌ Comparison currently available between curated hubs: <code>{', '.join(_DESTINATIONS_DB.keys())}</code>"
        )

    report = (
        f"⚖️ <b>Destination & Hotel Comparison</b>\n\n"
        f"<b>1. {d1['city']}</b>\n"
        f"• <b>Best Time:</b> {d1['best_season']}\n"
        f"• <b>Budget Tariff:</b> <code>{d1['avg_tariffs']['budget']}</code>\n"
        f"• <b>Luxury Tariff:</b> <code>{d1['avg_tariffs']['luxury']}</code>\n"
        f"• <b>Vibe:</b> <i>{d1['vibe']}</i>\n\n"
        f"<b>2. {d2['city']}</b>\n"
        f"• <b>Best Time:</b> {d2['best_season']}\n"
        f"• <b>Budget Tariff:</b> <code>{d2['avg_tariffs']['budget']}</code>\n"
        f"• <b>Luxury Tariff:</b> <code>{d2['avg_tariffs']['luxury']}</code>\n"
        f"• <b>Vibe:</b> <i>{d2['vibe']}</i>\n\n"
        f"<i>Check individual details with <code>.hotel {c1}</code> or <code>.hotel {c2}</code></i>"
    )
    await m.handle_message(report, parse_mode="html")


# ─── Assistant Bot Inline Query & Callback Handlers ──────────────────────────

if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_inline_query(pattern=r"^hotel(?::([a-z]+))?$")
    async def on_hotel_inline_query(event):
        match = event.pattern_match
        city_key = (match.group(1) or "goa").strip().lower()

        if city_key in _DESTINATIONS_DB:
            dest_data = _DESTINATIONS_DB[city_key]
            text = _render_destination_summary(dest_data, tier_filter=None, is_inline=True, city_key=city_key)
            buttons = _build_hotel_buttons(city_key)
            title = f"🏨 Hotels in {dest_data['city']}"
        else:
            text = _render_generic_city(city_key)
            buttons = []
            title = f"🏨 Hotels in {city_key.title()}"

        builder = event.builder
        result = builder.article(
            title=title,
            description="Explore luxury, mid-range, and budget stays with live tariffs",
            text=text,
            buttons=buttons if buttons else None,
            parse_mode="html",
            link_preview=False,
        )
        await event.answer([result], cache_time=30)


if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_callback_query(pattern=r"^htl:f:([a-z]+):(luxury|mid|budget|all)$")
    async def on_hotel_callback(event):
        data = event.data.decode("utf-8")
        _, _, city_key, tier = data.split(":")

        if city_key not in _DESTINATIONS_DB:
            return await event.answer("City not found", alert=True)

        tier_filter = None if tier == "all" else tier
        dest_data = _DESTINATIONS_DB[city_key]

        text = _render_destination_summary(dest_data, tier_filter, is_inline=True, city_key=city_key)
        buttons = _build_hotel_buttons(city_key)

        await event.answer(f"Loaded {tier.title()} Stays", alert=False)
        with contextlib.suppress(MessageNotModifiedError):
            await event.edit(text, buttons=buttons, parse_mode="html", link_preview=False)
