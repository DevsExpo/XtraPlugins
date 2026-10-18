# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import datetime
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

THEMES = {
    "dark": {"bg": (24, 37, 51), "bubble": (33, 50, 68), "text": (255, 255, 255), "name": (100, 181, 246)},
    "light": {"bg": (240, 242, 245), "bubble": (255, 255, 255), "text": (28, 30, 33), "name": (33, 150, 243)},
    "dracula": {"bg": (40, 42, 54), "bubble": (68, 71, 90), "text": (248, 248, 242), "name": (255, 121, 198)},
    "synthwave": {"bg": (26, 11, 46), "bubble": (42, 21, 74), "text": (249, 248, 255), "name": (255, 110, 199)},
    "emerald": {"bg": (6, 44, 36), "bubble": (13, 71, 57), "text": (230, 255, 245), "name": (100, 255, 180)},
    "midnight": {"bg": (15, 23, 42), "bubble": (30, 41, 59), "text": (241, 245, 249), "name": (56, 189, 248)},
}


def _get_font(size: int = 24, bold: bool = False):
    font_names = [
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "segoeui.ttf",
    ]
    for fn in font_names:
        try:
            return ImageFont.truetype(fn, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _render_local_quote(
    sender_name: str,
    text: str,
    avatar_path: Optional[str] = None,
    theme_key: str = "dark",
    time_str: str = "12:00",
) -> str:
    """Render a clean Telegram-style speech bubble card locally with Pillow."""
    palette = THEMES.get(theme_key, THEMES["dark"])

    font_name = _get_font(24, bold=True)
    font_text = _get_font(22, bold=False)
    font_time = _get_font(16, bold=False)

    # Word wrapping text
    max_bubble_width = 460
    words = text.split()
    lines = []
    cur_line = []

    for word in words:
        test_line = " ".join(cur_line + [word])
        # estimate width
        if len(test_line) * 12 > max_bubble_width:
            if cur_line:
                lines.append(" ".join(cur_line))
                cur_line = [word]
            else:
                lines.append(word)
                cur_line = []
        else:
            cur_line.append(word)
    if cur_line:
        lines.append(" ".join(cur_line))

    if not lines:
        lines = [""]

    line_height = 28
    text_block_height = len(lines) * line_height
    avatar_size = 64
    pad = 20

    bubble_width = max(280, min(500, max(len(ln) * 13 for ln in lines) + 60))
    bubble_height = max(avatar_size, 40 + text_block_height + 25)

    canvas_width = avatar_size + bubble_width + (pad * 3)
    canvas_height = max(avatar_size + (pad * 2), bubble_height + (pad * 2))

    # Base image
    img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw Avatar
    avatar_x = pad
    avatar_y = pad
    if avatar_path and os.path.exists(avatar_path):
        try:
            av = Image.open(avatar_path).convert("RGBA").resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
            img.paste(av, (avatar_x, avatar_y), mask)
        except Exception:
            avatar_path = None

    if not avatar_path or not os.path.exists(avatar_path):
        # Default placeholder circular avatar
        draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=palette["name"])
        initial = (sender_name[:1] or "?").upper()
        draw.text((avatar_x + 22, avatar_y + 14), initial, font=_get_font(30, bold=True), fill=(255, 255, 255))

    # Draw Speech Bubble
    bx = avatar_x + avatar_size + 14
    by = pad
    bw = bx + bubble_width
    bh = by + bubble_height

    # Rounded rectangle bubble
    draw.rounded_rectangle([bx, by, bw, bh], radius=18, fill=palette["bubble"])

    # Small pointer tail pointing towards avatar
    tail = [(bx, by + 18), (bx - 10, by + 26), (bx, by + 34)]
    draw.polygon(tail, fill=palette["bubble"])

    # Draw sender name
    draw.text((bx + 18, by + 14), sender_name, font=font_name, fill=palette["name"])

    # Draw text lines
    ty = by + 46
    for line in lines:
        draw.text((bx + 18, ty), line, font=font_text, fill=palette["text"])
        ty += line_height

    # Draw timestamp
    draw.text((bw - 60, bh - 24), time_str, font=font_time, fill=(160, 174, 192))

    out_path = os.path.join("temp/xtra_quote", f"quote_{datetime.datetime.now().strftime('%f')}.png")
    os.makedirs("temp/xtra_quote", exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


@Friday.register_on_cmd(
    ["quote", "q", "quotly"],
    cmd_help={
        "help": "Generate a beautiful Telegram-style speech bubble quote sticker or photo from replied message.",
        "example": "quote (replying to message)\nquote -sticker\nquote -theme synthwave\nquote -theme dracula (replying to message)",
    },
)
async def generate_quote(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)

    # Target message to quote
    target_msg = rm if rm else m
    quote_text = target_msg.text or (m.user_input.strip() if not rm else "")

    if not quote_text:
        return await m.handle_message(
            "❌ Please reply to a message containing text, or type text after <code>.quote &lt;text&gt;</code>."
        )

    raw = m.user_input.strip() if m.user_input else ""
    theme = "dark"
    as_sticker = "-sticker" in raw or "-s" in raw

    for tk in THEMES.keys():
        if f"-theme {tk}" in raw or f"-{tk}" in raw:
            theme = tk
            break

    msg = await m.handle_message(f"💬 Crafting quote bubble (Theme: <code>{theme.title()}</code>)...")
    os.makedirs("temp/xtra_quote", exist_ok=True)

    # Get sender info
    sender = await target_msg.get_sender()
    sender_name = "Anonymous"
    if sender:
        first = getattr(sender, "first_name", "") or ""
        last = getattr(sender, "last_name", "") or ""
        sender_name = f"{first} {last}".strip() or getattr(sender, "title", "Anonymous")

    time_str = "12:00"
    if hasattr(target_msg, "date") and target_msg.date:
        time_str = target_msg.date.strftime("%H:%M")

    # Download sender avatar
    avatar_file = None
    try:
        avatar_file = await c.download_profile_photo(sender, file="temp/xtra_quote/")
    except Exception:
        pass

    out_file = None
    try:
        # Local rendering engine guarantees instant zero-latency generation
        out_file = _render_local_quote(
            sender_name=sender_name,
            text=quote_text,
            avatar_path=avatar_file,
            theme_key=theme,
            time_str=time_str,
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        reply_to_id = rm.id if rm else m.id

        if as_sticker:
            # Convert to WebP sticker format
            webp_path = out_file.replace(".png", ".webp")
            stk_img = Image.open(out_file)
            stk_img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            stk_img.save(webp_path, "WEBP")

            await c.send_file(
                target_chat,
                webp_path,
                reply_to=reply_to_id,
            )
            if os.path.exists(webp_path):
                os.remove(webp_path)
        else:
            await c.send_file(
                target_chat,
                out_file,
                caption=f"💬 <b>Quote by {sender_name}</b>",
                reply_to=reply_to_id,
            )

        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Quote generation failed: <code>{e}</code>")
    finally:
        for fpath in (avatar_file, out_file):
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["quotethemes", "qthemes"],
    cmd_help={
        "help": "Display list of available color themes for message quotes.",
        "example": "quotethemes",
    },
)
async def list_quote_themes(c: Client, m: Message):
    theme_list = "\n".join([f"• <code>{th}</code>" for th in THEMES.keys()])
    text = (
        "🎨 <b>Available Quote Themes:</b>\n\n"
        f"{theme_list}\n\n"
        "<i>Usage:</i> <code>.quote -theme &lt;name&gt;</code> or <code>.quote -sticker -theme synthwave</code>"
    )
    await m.handle_message(text)
