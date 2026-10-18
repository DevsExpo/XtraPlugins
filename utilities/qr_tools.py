# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import urllib.parse
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import qrcode

    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from PIL import Image
    from pyzbar.pyzbar import decode as pyzbar_decode

    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@Friday.register_on_cmd(
    ["qr", "qrcode"],
    cmd_help={
        "help": "Generate a QR code from text or URL (or reply to a message).",
        "example": "qr https://github.com/FridaySoftware",
    },
)
async def generate_qr(c: Client, m: Message):
    text = m.user_input
    if not text:
        rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
        if rm and rm.text:
            text = rm.text
        elif rm and rm.caption:
            text = rm.caption

    if not text:
        return await m.handle_message("❌ Please provide text/URL to encode or reply to a text message.")

    msg = await m.handle_message("⚡ Generating QR code...")
    os.makedirs("temp/xtra_qr", exist_ok=True)
    out_path = f"temp/xtra_qr/qr_{m.id}.png"

    try:
        if HAS_QRCODE:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(out_path)
        elif HAS_HTTPX:
            # Fallback to web API if qrcode package is missing
            encoded = urllib.parse.quote_plus(text)
            url = f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&data={encoded}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    with open(out_path, "wb") as f:
                        f.write(res.content)
                else:
                    return await msg.edit_msg(f"❌ Failed to generate QR code (HTTP {res.status_code}).")
        else:
            return await msg.edit_msg("❌ Neither <code>qrcode</code> nor <code>httpx</code> is available.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        preview_text = text if len(text) <= 50 else f"{text[:47]}..."
        await c.send_file(
            target_chat,
            out_path,
            caption=f"📱 <b>QR Code Generated</b>\n<b>Content:</b> <code>{preview_text}</code>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Error generating QR code: <code>{e}</code>")
    finally:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["qrscan", "readqr", "decodeqr"],
    cmd_help={
        "help": "Read and decode a QR code from a replied image or sticker.",
        "example": "qrscan (replying to QR code image)",
    },
    requires_reply=True,
)
async def scan_qr(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (
        rm.photo or rm.sticker or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("image/"))
    ):
        return await m.handle_message("❌ Please reply to a photo or image containing a QR code.")

    msg = await m.handle_message("🔍 Downloading and scanning QR code...")
    os.makedirs("temp/xtra_qr", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_qr/")

    if not download_path or not os.path.exists(download_path):
        return await msg.edit_msg("❌ Failed to download QR image.")

    decoded_text = None

    try:
        # First attempt: local pyzbar if available
        if HAS_PYZBAR:
            try:
                img = Image.open(download_path)
                results = pyzbar_decode(img)
                if results:
                    decoded_text = results[0].data.decode("utf-8", errors="replace")
            except Exception:
                decoded_text = None

        # Second attempt: reliable online decoding API
        if not decoded_text:
            if not HAS_HTTPX:
                return await msg.edit_msg("❌ <code>httpx</code> is required for QR code decoding.")

            async with httpx.AsyncClient(timeout=20.0) as client:
                with open(download_path, "rb") as f:
                    files = {"file": (os.path.basename(download_path), f, "image/png")}
                    res = await client.post("https://api.qrserver.com/v1/read-qr-code/", files=files)

                if res.status_code == 200:
                    data = res.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        symbol = data[0].get("symbol", [])
                        if symbol and len(symbol) > 0:
                            data_field = symbol[0].get("data")
                            error_field = symbol[0].get("error")
                            if data_field:
                                decoded_text = data_field
                            elif error_field:
                                return await msg.edit_msg(f"❌ QR Scan failed: <i>{error_field}</i>")

        if not decoded_text:
            return await msg.edit_msg("❌ No QR code could be detected or read in this image.")

        result_msg = f"<b>📱 QR Code Decoded Result:</b>\n\n<code>{decoded_text}</code>"
        await msg.edit_msg(result_msg)
    except Exception as e:
        await msg.edit_msg(f"❌ Error during QR scanning: <code>{e}</code>")
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass
