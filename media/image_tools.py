# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import random
import asyncio
from pathlib import Path
from time import perf_counter as pc
from typing import Optional, Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _check_pil():
    if not HAS_PIL:
        raise RuntimeError("Pillow is not installed. Run 'pip install pillow' to use image tools.")


async def _download_replied_image(m: Message) -> Tuple[Optional[str], Optional[str]]:
    """Helper to download replied photo or sticker and return local path and temp dir."""
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (
        rm.photo or rm.sticker or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("image/"))
    ):
        return None, None
    os.makedirs("temp/xtra_images", exist_ok=True)
    file_path = await rm.download_media("temp/xtra_images/")
    return file_path, "temp/xtra_images"


@Friday.register_on_cmd(
    ["iresize"],
    cmd_help={
        "help": "Resize an image or sticker to specific dimensions.",
        "example": "iresize 512x512 (replying to image)",
    },
    requires_reply=True,
    requires_input=True,
)
async def image_resize(c: Client, m: Message):
    _check_pil()
    msg = await m.handle_message("Processing image resize...")
    raw = m.user_input.lower().replace(" ", "x")
    try:
        parts = raw.split("x")
        w, h = int(parts[0]), int(parts[1])
    except Exception:
        return await msg.edit_msg("❌ Please provide valid dimensions, e.g. <code>512x512</code>")

    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image, photo, or sticker.")

    out_path = f"{file_path}_resized.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                res = img.resize((w, h), Image.Resampling.LANCZOS)
                res.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(
            m.chat.id, out_path, caption=f"📐 Resized to <code>{w}x{h}</code>", reply_to=m.reply_to_message.id
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to resize image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["iblur"],
    cmd_help={
        "help": "Apply a Gaussian blur filter to an image.",
        "example": "iblur 15 (replying to image)",
    },
    requires_reply=True,
)
async def image_blur(c: Client, m: Message):
    _check_pil()
    msg = await m.handle_message("Applying blur effect...")
    radius = 10
    if m.user_input and m.user_input.isdigit():
        radius = min(int(m.user_input), 100)

    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_blur.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
                blurred.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(
            m.chat.id, out_path, caption=f"🌫️ Blurred (radius: <code>{radius}</code>)", reply_to=m.reply_to_message.id
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to blur image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["iinvert", "inegative"],
    cmd_help={
        "help": "Invert image colors (negative effect).",
        "example": "iinvert (replying to image)",
    },
    requires_reply=True,
)
async def image_invert(c: Client, m: Message):
    _check_pil()
    msg = await m.handle_message("Inverting image colors...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_inverted.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                rgb_img = img.convert("RGB")
                inv = ImageOps.invert(rgb_img)
                inv.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(m.chat.id, out_path, caption="🔄 Inverted colors", reply_to=m.reply_to_message.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to invert image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["igray", "igrayscale", "ibw"],
    cmd_help={
        "help": "Convert an image to grayscale / black and white.",
        "example": "igray (replying to image)",
    },
    requires_reply=True,
)
async def image_gray(c: Client, m: Message):
    _check_pil()
    msg = await m.handle_message("Converting to grayscale...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_gray.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                gray = ImageOps.grayscale(img)
                gray.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(m.chat.id, out_path, caption="🎞️ Grayscale conversion", reply_to=m.reply_to_message.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to convert image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["iflip", "imirror"],
    cmd_help={
        "help": "Flip or mirror an image horizontally or vertically.",
        "example": "iflip (horizontal) or iflip -v (vertical)",
        "user_args": [
            {
                "arg": "v",
                "help": "Flip vertically instead of horizontally.",
                "requires_input": False,
            }
        ],
    },
    requires_reply=True,
)
async def image_flip(c: Client, m: Message):
    _check_pil()
    msg = await m.handle_message("Flipping image...")
    vertical = "v" in m.user_args
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_flipped.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                if vertical:
                    flipped = ImageOps.flip(img)
                else:
                    flipped = ImageOps.mirror(img)
                flipped.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        direction = "Vertically" if vertical else "Horizontally"
        await c.send_file(m.chat.id, out_path, caption=f"🪞 Flipped {direction}", reply_to=m.reply_to_message.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to flip image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["irotate"],
    cmd_help={
        "help": "Rotate an image by specified degrees (e.g. 90, 180, 270).",
        "example": "irotate 90 (replying to image)",
    },
    requires_reply=True,
)
async def image_rotate(c: Client, m: Message):
    _check_pil()
    degrees = 90
    if m.user_input and m.user_input.lstrip("-").isdigit():
        degrees = int(m.user_input)

    msg = await m.handle_message(f"Rotating image by {degrees}°...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_rotated.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                rotated = img.rotate(degrees, expand=True)
                rotated.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(m.chat.id, out_path, caption=f"🔄 Rotated {degrees}°", reply_to=m.reply_to_message.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to rotate image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["icircle", "iround"],
    cmd_help={
        "help": "Crop an image into a circle with transparent background (perfect for avatars/stickers).",
        "example": "icircle (replying to image)",
    },
    requires_reply=True,
)
async def image_circle(c: Client, m: Message):
    _check_pil()
    msg = await m.handle_message("Creating circular crop...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_circle.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                img = img.convert("RGBA")
                size = min(img.size)
                # Crop to square
                left = (img.width - size) // 2
                top = (img.height - size) // 2
                img = img.crop((left, top, left + size, top + size))

                # Create circular alpha mask
                mask = Image.new("L", (size, size), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, size, size), fill=255)

                result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                result.paste(img, (0, 0), mask=mask)
                result.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(m.chat.id, out_path, caption="⚪ Circular avatar crop", reply_to=m.reply_to_message.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to circle crop image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["iwatermark", "itext"],
    cmd_help={
        "help": "Add a text watermark overlay to the bottom of an image.",
        "example": "iwatermark Copyright 2026 (replying to image)",
    },
    requires_reply=True,
    requires_input=True,
)
async def image_watermark(c: Client, m: Message):
    _check_pil()
    watermark_text = m.user_input.strip()
    msg = await m.handle_message("Adding watermark...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    out_path = f"{file_path}_watermark.png"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                img = img.convert("RGBA")
                draw = ImageDraw.Draw(img)
                # Dynamic font sizing
                font_size = max(int(img.height * 0.04), 16)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except Exception:
                    font = ImageFont.load_default()

                # Get bbox for positioning
                bbox = draw.textbbox((0, 0), watermark_text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                x = img.width - text_w - 20
                y = img.height - text_h - 20

                # Subtle shadow then text
                draw.text((x + 2, y + 2), watermark_text, fill=(0, 0, 0, 180), font=font)
                draw.text((x, y), watermark_text, fill=(255, 255, 255, 230), font=font)
                img.save(out_path, format="PNG")

        await loop.run_in_executor(None, _process)
        await c.send_file(
            m.chat.id, out_path, caption=f"✍️ Watermarked: <i>{watermark_text}</i>", reply_to=m.reply_to_message.id
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to add watermark: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["icompress"],
    cmd_help={
        "help": "Compress an image with specified JPEG quality (1-100, default 50).",
        "example": "icompress 40 (replying to image)",
    },
    requires_reply=True,
)
async def image_compress(c: Client, m: Message):
    _check_pil()
    quality = 50
    if m.user_input and m.user_input.isdigit():
        quality = max(1, min(int(m.user_input), 95))

    msg = await m.handle_message(f"Compressing image (quality: {quality}%)...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image or photo.")

    original_size = os.path.getsize(file_path)
    out_path = f"{file_path}_compressed.jpg"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                rgb_img = img.convert("RGB")
                rgb_img.save(out_path, format="JPEG", quality=quality, optimize=True)

        await loop.run_in_executor(None, _process)

        compressed_size = os.path.getsize(out_path)
        saved = max(0, original_size - compressed_size)
        pct = (saved / original_size) * 100 if original_size else 0

        cap = (
            f"🗜️ <b>Image Compressed:</b>\n"
            f"• <b>Original:</b> <code>{original_size // 1024} KB</code>\n"
            f"• <b>New:</b> <code>{compressed_size // 1024} KB</code>\n"
            f"• <b>Saved:</b> <code>{pct:.1f}%</code>"
        )
        await c.send_file(m.chat.id, out_path, caption=cap, reply_to=m.reply_to_message.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to compress image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["iconvert"],
    cmd_help={
        "help": "Convert an image to a different format (png, jpg, webp, ico, bmp).",
        "example": "iconvert png (replying to sticker/webp) or iconvert webp",
    },
    requires_reply=True,
    requires_input=True,
)
async def image_convert(c: Client, m: Message):
    _check_pil()
    fmt = m.user_input.lower().strip().lstrip(".")
    valid_formats = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "ico": "ICO", "bmp": "BMP"}
    if fmt not in valid_formats:
        return await m.handle_message(f"❌ Unsupported format. Supported: {', '.join(valid_formats.keys())}")

    msg = await m.handle_message(f"Converting image to {fmt.upper()}...")
    file_path, _ = await _download_replied_image(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid image, photo, or sticker.")

    target_pil_fmt = valid_formats[fmt]
    out_path = f"{file_path}.{fmt}"
    try:
        loop = asyncio.get_running_loop()

        def _process():
            with Image.open(file_path) as img:
                if target_pil_fmt == "JPEG" and img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(out_path, format=target_pil_fmt)

        await loop.run_in_executor(None, _process)
        await c.send_file(
            m.chat.id, out_path, caption=f"📁 Converted to <b>{fmt.upper()}</b>", reply_to=m.reply_to_message.id
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to convert image: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if os.path.exists(p):
                os.remove(p)


LOGO_COLOURS = [
    (255, 0, 0),
    (255, 64, 0),
    (255, 128, 0),
    (255, 191, 0),
    (255, 255, 0),
    (191, 255, 0),
    (128, 255, 0),
    (64, 255, 0),
    (0, 255, 0),
    (0, 255, 64),
    (0, 255, 128),
    (0, 255, 191),
    (0, 255, 255),
    (0, 191, 255),
    (0, 128, 255),
    (0, 64, 255),
    (0, 0, 255),
    (64, 0, 255),
    (128, 0, 255),
    (191, 0, 255),
    (255, 0, 255),
    (255, 0, 191),
    (255, 0, 128),
    (255, 0, 64),
]


@Friday.register_on_cmd(
    ["logo"],
    cmd_help={
        "help": "Generate a stylized logo graphic with custom text, font size, and RGB color.",
        "example": "logo Friday|120|255 0 102",
    },
)
async def logo_gen(c: Client, m: Message):
    _check_pil()
    start_ = pc()
    msg = await m.handle_message("🎨 Generating custom logo...")
    raw = m.user_input or "Friday"
    parts = raw.split("|")
    text = parts[0].strip() or "Friday"
    size = 120
    if len(parts) > 1 and parts[1].strip().isdigit():
        size = max(20, min(300, int(parts[1].strip())))

    color = random.choice(LOGO_COLOURS)
    if len(parts) > 2:
        rgb_raw = parts[2].strip().split()
        if len(rgb_raw) >= 3 and all(x.isdigit() for x in rgb_raw[:3]):
            color = (int(rgb_raw[0]), int(rgb_raw[1]), int(rgb_raw[2]))

    temp_dir = os.path.abspath("temp/xtra_images")
    os.makedirs(temp_dir, exist_ok=True)
    out_file = os.path.join(temp_dir, f"logo_{m.id}_{int(start_)}.png")

    try:

        def _render():
            assets_path = Path(__file__).resolve().parents[1] / "assets"
            blank_img_path = assets_path / "images" / "blank_black.png"
            if not blank_img_path.exists():
                blank_img_path = Path(__file__).resolve().parents[2] / "Main" / "assets" / "images" / "blank_black.png"

            font_path = assets_path / "fonts" / "Streamster.ttf"
            if not font_path.exists():
                font_path = Path(__file__).resolve().parents[2] / "Main" / "assets" / "fonts" / "Streamster.ttf"

            if blank_img_path.exists():
                img = Image.open(blank_img_path).convert("RGBA")
            else:
                img = Image.new("RGBA", (1920, 1080), (15, 15, 20, 255))

            try:
                if font_path.exists():
                    font = ImageFont.truetype(str(font_path), size)
                else:
                    font = ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            draw = ImageDraw.Draw(img)
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                w, h = draw.textsize(text, font=font)

            x = (img.width - w) // 2
            y = (img.height - h) // 2
            draw.text((x, y), text, fill=color, font=font)
            img.save(out_file, "PNG")

        await asyncio.get_running_loop().run_in_executor(None, _render)

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_file,
            caption=f"🎨 <b>Logo Generated:</b> <code>{text}</code>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to generate logo: <code>{e}</code>")
    finally:
        if os.path.exists(out_file):
            try:
                os.remove(out_file)
            except Exception:
                pass
