# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import io
import logging
import os
from typing import List, Optional, Tuple

import aiohttp

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors

logger = logging.getLogger("friday.chart_tools")


_PALETTE = [
    "rgba(54, 162, 235, 0.8)",
    "rgba(255, 99, 132, 0.8)",
    "rgba(255, 206, 86, 0.8)",
    "rgba(75, 192, 192, 0.8)",
    "rgba(153, 102, 255, 0.8)",
    "rgba(255, 159, 64, 0.8)",
    "rgba(46, 204, 113, 0.8)",
    "rgba(231, 76, 60, 0.8)",
    "rgba(52, 152, 219, 0.8)",
    "rgba(155, 89, 182, 0.8)",
]

_BORDER_PALETTE = [c.replace("0.8", "1.0") for c in _PALETTE]


def _parse_chart_input(raw: str) -> Tuple[str, List[str], List[float], str]:
    """Parse chart input supporting multiple user formats."""
    parts = raw.strip().split(None, 1)
    chart_type = parts[0].lower() if parts else "bar"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if chart_type in ("doughnut", "donut"):
        chart_type = "doughnut"
    elif chart_type not in ("bar", "line", "pie", "doughnut", "radar"):
        # Default to bar if user started directly with data
        rest = raw.strip()
        chart_type = "bar"

    labels: List[str] = []
    values: List[float] = []
    title = f"{chart_type.capitalize()} Chart"

    if "|" in rest:
        l_part, v_part = rest.split("|", 1)
        labels = [x.strip() for x in l_part.split(",") if x.strip()]
        for v in v_part.split(","):
            try:
                values.append(float(v.strip()))
            except ValueError:
                pass
    # Check for Key-Value format: "Label1:10, Label2:20"
    elif ":" in rest:
        items = [x.strip() for x in rest.split(",") if x.strip()]
        for it in items:
            if ":" in it:
                k, v = it.split(":", 1)
                labels.append(k.strip())
                try:
                    values.append(float(v.strip()))
                except ValueError:
                    values.append(0.0)
    else:
        num_parts = [x.strip() for x in rest.replace(" ", ",").split(",") if x.strip()]
        for idx, np in enumerate(num_parts):
            try:
                val = float(np)
                values.append(val)
                labels.append(f"#{idx + 1}")
            except ValueError:
                pass

    if len(labels) < len(values):
        labels.extend([f"Item {i + 1}" for i in range(len(labels), len(values))])
    elif len(values) < len(labels):
        labels = labels[: len(values)]

    return chart_type, labels, values, title


async def _render_chart_image(chart_type: str, labels: List[str], values: List[float], title: str) -> Optional[bytes]:
    """Render chart via QuickChart API with dark theme styling."""
    if not labels or not values:
        return None

    # Construct Chart.js configuration
    chart_config = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": title,
                    "data": values,
                    "backgroundColor": _PALETTE[: len(values)],
                    "borderColor": _BORDER_PALETTE[: len(values)],
                    "borderWidth": 2,
                    "fill": (chart_type == "line"),
                }
            ],
        },
        "options": {
            "responsive": True,
            "title": {
                "display": True,
                "text": title,
                "fontColor": "#ffffff",
                "fontSize": 16,
            },
            "legend": {
                "display": (chart_type in ("pie", "doughnut", "radar")),
                "labels": {"fontColor": "#cccccc"},
            },
            "scales": (
                {
                    "xAxes": [{"ticks": {"fontColor": "#aaaaaa"}, "gridLines": {"color": "rgba(255,255,255,0.1)"}}],
                    "yAxes": [
                        {
                            "ticks": {"fontColor": "#aaaaaa", "beginAtZero": True},
                            "gridLines": {"color": "rgba(255,255,255,0.1)"},
                        }
                    ],
                }
                if chart_type in ("bar", "line")
                else {}
            ),
        },
    }

    payload = {
        "backgroundColor": "#181a1f",
        "width": 800,
        "height": 450,
        "format": "png",
        "chart": chart_config,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://quickchart.io/chart", json=payload) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as exc:
        logger.warning(f"QuickChart API request failed: {exc}")

    # Fallback to local Matplotlib if QuickChart is unreachable
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)
        fig.patch.set_facecolor("#181a1f")
        ax.set_facecolor("#181a1f")

        if chart_type == "line":
            ax.plot(labels, values, marker="o", color="#00bcd4", linewidth=2.5)
        elif chart_type in ("pie", "doughnut"):
            ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=140)
        else:
            ax.bar(labels, values, color="#3498db", edgecolor="#2980b9")

        ax.set_title(title, color="white", fontsize=14, pad=12)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as exc:
        logger.error(f"Local matplotlib chart fallback failed: {exc}")
        return None


@Friday.register_on_cmd(
    ["chart", "plot", "graph"],
    cmd_help={
        "help": "Generate high-resolution data visualization charts (bar, line, pie, donut, radar) and send as photo.",
        "example": [
            "chart bar Jan,Feb,Mar,Apr | 15,28,42,35",
            "chart pie Bitcoin:45, Ethereum:30, Solana:15, USDT:10",
            "chart line 10, 25, 18, 42, 60, 55, 80",
            "chart donut UI:40, Backend:35, Testing:25",
            "chart radar Speed:80, Power:95, Defense:70, Agility:85",
        ],
    },
    requires_input=True,
)
@log_errors
async def chart_cmd(c: Client, m: Message):
    raw_input = m.user_input.strip()
    status_msg = await m.handle_message("📊 <i>Rendering high-definition chart...</i>")

    chart_type, labels, values, title = _parse_chart_input(raw_input)
    if not values:
        return await status_msg.edit_msg(
            "❌ <b>Invalid chart data format.</b>\n\n"
            "<b>Usage Examples:</b>\n"
            "• <code>.chart bar Jan,Feb,Mar | 10,20,30</code>\n"
            "• <code>.chart pie BTC:45, ETH:30, SOL:25</code>\n"
            "• <code>.chart line 12, 19, 3, 5, 2, 24</code>"
        )

    img_bytes = await _render_chart_image(chart_type, labels, values, title)
    if not img_bytes:
        return await status_msg.edit_msg("❌ Failed to render chart image. Please verify data values.")

    target_chat = m.chat_id or getattr(m.chat, "id", None)
    os.makedirs("temp/xtra_charts", exist_ok=True)
    temp_fn = f"temp/xtra_charts/chart_{m.id}.png"

    try:
        with open(temp_fn, "wb") as f:
            f.write(img_bytes)

        val_summary = ", ".join(f"{k}: <b>{v:g}</b>" for k, v in zip(labels[:6], values[:6]))
        caption = (
            f"📊 <b>{title}</b> ({chart_type.upper()})\n\n"
            f"• <b>Data points ({len(values)}):</b> {val_summary}\n"
            f"• <b>Total Sum:</b> <code>{sum(values):g}</code> | <b>Average:</b> <code>{sum(values) / len(values):.2f}</code>"
        )

        await c.send_file(target_chat, temp_fn, caption=caption, reply_to=m.id)
        await status_msg.delete_if_self()
    finally:
        if os.path.exists(temp_fn):
            os.remove(temp_fn)


# ─── Growth, Percentage & Financial Metrics ──────────────────────────────────


@Friday.register_on_cmd(
    ["cagr", "annualgrowth"],
    cmd_help={
        "help": "Calculate Compound Annual Growth Rate (CAGR) given beginning value, ending value, and number of years.",
        "example": ["cagr 10000 25000 5 (10k to 25k in 5 years)"],
    },
    requires_input=True,
)
@log_errors
async def cagr_cmd(c: Client, m: Message):
    parts = m.user_input.strip().split()
    if len(parts) < 3:
        return await m.handle_message(
            "❌ Usage: <code>.cagr &lt;initial_val&gt; &lt;final_val&gt; &lt;years&gt;</code> (e.g. <code>.cagr 10000 25000 5</code>)"
        )

    try:
        v_init = float(parts[0])
        v_final = float(parts[1])
        years = float(parts[2])
    except ValueError:
        return await m.handle_message("❌ All arguments must be valid numbers.")

    if v_init <= 0 or v_final <= 0 or years <= 0:
        return await m.handle_message("❌ Values and years must be positive numbers.")

    cagr_val = ((v_final / v_init) ** (1.0 / years) - 1.0) * 100
    report = (
        f"📈 <b>Compound Annual Growth Rate (CAGR)</b>\n\n"
        f"• <b>Beginning Value:</b> <code>{v_init:,.2f}</code>\n"
        f"• <b>Ending Value:</b> <code>{v_final:,.2f}</code>\n"
        f"• <b>Time Horizon:</b> <code>{years:g} years</code>\n"
        f"• <b>CAGR:</b> <b>{cagr_val:+.2f}% / year</b>\n"
        f"• <b>Total Return:</b> <code>{((v_final - v_init) / v_init) * 100:+.2f}%</code>"
    )
    await m.handle_message(report, parse_mode="html")


@Friday.register_on_cmd(
    ["calcpercent", "pct", "growth"],
    cmd_help={
        "help": "Calculate percentage change, profit margin, or ratio between two values.",
        "example": [
            "growth 150 220 (percentage change from 150 to 220)",
            "growth 500 420",
        ],
    },
    requires_input=True,
)
@log_errors
async def growth_calculator_cmd(c: Client, m: Message):
    parts = m.user_input.strip().split()
    if len(parts) < 2:
        return await m.handle_message("❌ Usage: <code>.growth &lt;initial_value&gt; &lt;final_value&gt;</code>")

    try:
        v1 = float(parts[0])
        v2 = float(parts[1])
    except ValueError:
        return await m.handle_message("❌ Both inputs must be valid numbers.")

    if v1 == 0:
        return await m.handle_message("❌ Initial value cannot be zero.")

    diff = v2 - v1
    pct = (diff / abs(v1)) * 100
    icon = "📈" if diff >= 0 else "📉"
    trend = "Increase / Gain" if diff >= 0 else "Decrease / Loss"

    report = (
        f"{icon} <b>Growth & Percentage Metrics</b>\n\n"
        f"• <b>Initial:</b> <code>{v1:g}</code>\n"
        f"• <b>Final:</b> <code>{v2:g}</code>\n"
        f"• <b>Absolute Delta:</b> <code>{diff:+g}</code>\n"
        f"• <b>Percentage Change:</b> <b>{pct:+.2f}%</b> ({trend})\n"
        f"• <b>Multiplier:</b> <code>{v2 / v1:.3f}x</code>"
    )
    await m.handle_message(report, parse_mode="html")
