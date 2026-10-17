# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
from typing import Optional, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

CARBON_THEMES = {
    "dracula": {
        "bg": (40, 42, 54),
        "card": (30, 32, 42),
        "text": (248, 248, 242),
        "lineno": (98, 114, 164),
        "bar": (33, 34, 44),
    },
    "monokai": {
        "bg": (39, 40, 34),
        "card": (27, 28, 24),
        "text": (248, 248, 240),
        "lineno": (117, 113, 94),
        "bar": (30, 31, 26),
    },
    "nord": {
        "bg": (46, 52, 64),
        "card": (36, 41, 51),
        "text": (236, 239, 244),
        "lineno": (76, 86, 106),
        "bar": (41, 46, 57),
    },
    "synthwave": {
        "bg": (38, 25, 60),
        "card": (24, 15, 40),
        "text": (255, 126, 219),
        "lineno": (97, 66, 137),
        "bar": (20, 11, 35),
    },
    "one_dark": {
        "bg": (40, 44, 52),
        "card": (33, 37, 43),
        "text": (171, 178, 191),
        "lineno": (92, 99, 112),
        "bar": (28, 31, 36),
    },
}


def _get_mono_font(size: int = 22):
    font_candidates = [
        "consola.ttf",
        "consolas.ttf",
        "DejaVuSansMono.ttf",
        "cour.ttf",
        "arial.ttf",
    ]
    for fc in font_candidates:
        try:
            return ImageFont.truetype(fc, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _render_styled_carbon(
    code: str,
    out_path: str,
    theme_key: str = "dracula",
    title: str = "snippet.py",
    show_lines: bool = True,
) -> None:
    theme = CARBON_THEMES.get(theme_key, CARBON_THEMES["dracula"])
    lines = code.splitlines() or [""]

    font_code = _get_mono_font(22)
    font_title = _get_mono_font(18)
    font_lineno = _get_mono_font(20)

    char_w = 14
    line_h = 32
    max_line_len = max(len(l) for l in lines)

    lineno_col_w = 60 if show_lines else 20
    content_w = max(550, (max_line_len * char_w) + lineno_col_w + 60)
    bar_h = 44
    content_h = bar_h + (len(lines) * line_h) + 40

    pad = 40
    img_w = content_w + (pad * 2)
    img_h = content_h + (pad * 2)

    img = Image.new("RGBA", (img_w, img_h), theme["bg"])
    draw = ImageDraw.Draw(img)

    # Window card
    cx1, cy1 = pad, pad
    cx2, cy2 = img_w - pad, img_h - pad
    draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=16, fill=theme["card"])

    # Title bar
    draw.rounded_rectangle([cx1, cy1, cx2, cy1 + bar_h], radius=16, fill=theme["bar"])
    draw.rectangle([cx1, cy1 + bar_h - 10, cx2, cy1 + bar_h], fill=theme["bar"])

    # macOS window traffic light buttons
    btn_y = cy1 + 22
    draw.ellipse([cx1 + 20, btn_y - 6, cx1 + 32, btn_y + 6], fill=(255, 95, 86))
    draw.ellipse([cx1 + 42, btn_y - 6, cx1 + 54, btn_y + 6], fill=(255, 189, 46))
    draw.ellipse([cx1 + 64, btn_y - 6, cx1 + 76, btn_y + 6], fill=(39, 201, 63))

    # Title text
    draw.text((cx1 + 100, cy1 + 12), title, font=font_title, fill=(180, 190, 205))

    # Code lines
    curr_y = cy1 + bar_h + 20
    for idx, line in enumerate(lines, 1):
        if show_lines:
            draw.text((cx1 + 24, curr_y), f"{idx:2d}", font=font_lineno, fill=theme["lineno"])
            code_x = cx1 + lineno_col_w + 20
        else:
            code_x = cx1 + 30

        draw.text((code_x, curr_y), line, font=font_code, fill=theme["text"])
        curr_y += line_h

    img.save(out_path, "PNG")


@Friday.register_on_cmd(
    ["carbon", "carbonsh", "codeimg"],
    cmd_help={
        "help": "Generate a beautiful Carbon-style code snippet graphic with customizable themes, line numbers, and window title.",
        "example": "carbon print('Hello')\ncarbon -theme synthwave -title main.py\ncarbon -theme nord -nolines (replying to code)",
    },
)
async def generate_carbon(c: Client, m: Message):
    raw = (m.user_input or "").strip()
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)

    theme = "dracula"
    title = "snippet.py"
    show_lines = True

    if "-theme " in raw:
        parts = raw.split("-theme ")
        raw = parts[0].strip()
        theme_cand = parts[1].strip().split()[0].lower()
        if theme_cand in CARBON_THEMES:
            theme = theme_cand

    if "-title " in raw:
        parts = raw.split("-title ")
        raw = parts[0].strip()
        title = parts[1].strip().split()[0]

    if "-nolines" in raw or "-noline" in raw:
        show_lines = False
        raw = raw.replace("-nolines", "").replace("-noline", "").strip()

    code = raw
    if not code and rm:
        code = rm.text or rm.caption or ""

    if not code:
        return await m.handle_message("❌ Please provide code or reply to a code message.")

    msg = await m.handle_message(f"🎨 Rendering Carbon code card (Theme: <code>{theme.title()}</code>)...")
    os.makedirs("temp/xtra_carbon", exist_ok=True)
    out_file = f"temp/xtra_carbon/carbon_{m.id}.png"

    try:
        _render_styled_carbon(
            code=code,
            out_path=out_file,
            theme_key=theme,
            title=title,
            show_lines=show_lines,
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_file,
            caption=f"💻 <b>Carbon Snippet</b> (<code>{title}</code> • {theme.title()})",
            reply_to=m.id,
        )
        try:
            await msg.delete()
        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Carbon generation failed: <code>{e}</code>")
    finally:
        if os.path.exists(out_file):
            try:
                os.remove(out_file)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["carbonthemes"],
    cmd_help={
        "help": "List available syntax window themes for carbon code generation.",
        "example": "carbonthemes",
    },
)
async def list_carbon_themes(c: Client, m: Message):
    themes = "\n".join([f"• <code>{th}</code>" for th in CARBON_THEMES.keys()])
    await m.handle_message(
        f"🎨 <b>Available Carbon Themes:</b>\n\n{themes}\n\n<i>Usage:</i> <code>.carbon -theme synthwave print('Friday')</code>"
    )
