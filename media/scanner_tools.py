# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import asyncio
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    from PIL import Image, ImageOps, ImageEnhance

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _check_pil():
    if not HAS_PIL:
        raise RuntimeError("Pillow is required for document scanning.")


def _apply_scanner_effect(input_path: str, output_path: str) -> None:
    """Enhance and threshold an image to look like a scanned physical document."""
    with Image.open(input_path) as img:
        # Convert to grayscale
        gray = img.convert("L")

        # Auto-contrast to eliminate background shadowing
        autocontrasted = ImageOps.autocontrast(gray, cutoff=2)

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(autocontrasted)
        high_contrast = enhancer.enhance(1.8)

        # Enhance sharpness
        sharpener = ImageEnhance.Sharpness(high_contrast)
        sharp = sharpener.enhance(1.5)

        # Clean thresholding to turn off-white paper pure white and ink dark
        def _thresh(val):
            return 255 if val > 165 else int(val * 0.7)

        scanned = sharp.point(_thresh)
        scanned.save(output_path, "PNG")


@Friday.register_on_cmd(
    ["docscan", "scanner", "scan"],
    cmd_help={
        "help": "Transform a photo of a paper or document into a clean, high-contrast scanned document.",
        "example": "docscan (replying to photo/document)",
    },
    requires_reply=True,
)
async def document_scan(c: Client, m: Message):
    _check_pil()
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (rm.photo or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("image/"))):
        return await m.handle_message("❌ Please reply to a photo or image of a document to scan.")

    msg = await m.handle_message("📑 Processing document scan...")
    os.makedirs("temp/xtra_scanner", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_scanner/")

    if not download_path or not os.path.exists(download_path):
        return await msg.edit_msg("❌ Failed to download replied image.")

    out_scanned = f"temp/xtra_scanner/scanned_{m.id}.png"

    try:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: _apply_scanner_effect(download_path, out_scanned)
        )

        if not os.path.exists(out_scanned):
            return await msg.edit_msg("❌ Scanner processing failed.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_scanned,
            caption="📑 <b>Document Scanned Successfully</b>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Error during document scanning: <code>{e}</code>")
    finally:
        for p in (download_path, out_scanned):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
