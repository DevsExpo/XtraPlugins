# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import os
import io
import asyncio
from typing import Optional
from PIL import Image, ImageColor

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import rembg

    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False


def _remove_background_local(input_bytes: bytes, bg_color: Optional[str] = None) -> bytes:
    """Removes background using local AI rembg (zero API key needed)."""
    if HAS_REMBG:
        output_bytes = rembg.remove(input_bytes)
        img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    else:
        # Fallback if rembg is not installed yet: sample corners and create mask
        img = Image.open(io.BytesIO(input_bytes)).convert("RGBA")
        datas = img.getdata()
        corner = datas[0]
        new_data = []
        tolerance = 30
        for item in datas:
            if all(abs(item[i] - corner[i]) <= tolerance for i in range(3)):
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)

    if bg_color:
        try:
            col = ImageColor.getrgb(bg_color)
            background = Image.new("RGBA", img.size, (*col, 255))
            background.paste(img, (0, 0), img)
            img = background.convert("RGB")
            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=95)
            return out_buf.getvalue()
        except Exception:
            pass

    out_buf = io.BytesIO()
    img.save(out_buf, format="PNG")
    return out_buf.getvalue()


@Friday.register_on_cmd(
    ["rmbg", "removebg", "nobg"],
    cmd_help={
        "help": "Remove image background locally without any external paid API (100% free offline AI via rembg).",
        "example": "rmbg (reply to photo for transparent PNG)\nrmbg white (reply to photo for solid white background)\nrmbg #00FFAA (reply to photo for custom hex background)",
    },
    requires_reply=True,
)
async def remove_bg_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.photo or reply.sticker or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to a photo or image sticker to remove its background.")

    bg_color = (m.user_input or "").strip() or None
    status_text = (
        "🪄 Removing background (AI offline)..."
        if not bg_color
        else f"🪄 Removing background & applying <b>{bg_color}</b> fill..."
    )
    msg = await m.handle_message(status_text)

    out_dir = os.path.join("temp", "rmbg")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download replied image.")

    try:
        with open(input_file, "rb") as f:
            raw_bytes = f.read()

        loop = asyncio.get_running_loop()
        processed_bytes = await loop.run_in_executor(None, _remove_background_local, raw_bytes, bg_color)

        ext = ".jpg" if bg_color else ".png"
        out_file = os.path.join(out_dir, f"no_bg_{os.path.basename(input_file)}{ext}")
        with open(out_file, "wb") as f:
            f.write(processed_bytes)

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        engine_badge = (
            "Rembg AI (Local)"
            if HAS_REMBG
            else "Color Mask (Install rembg for AI model: <code>pip install rembg</code>)"
        )
        caption = f"✨ <b>Background Removed</b>\n• Engine: <code>{engine_badge}</code>"
        if bg_color:
            caption += f"\n• Color Fill: <code>{bg_color}</code>"

        await c.send_file(
            target_chat,
            out_file,
            caption=caption,
            force_document=not bool(bg_color),
            reply_to=reply.id,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"❌ Background removal error: <code>{e}</code>")
    finally:
        for f in [input_file, locals().get("out_file")]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
