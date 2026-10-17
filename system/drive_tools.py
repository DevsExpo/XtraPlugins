# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import re
from typing import Optional, Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.utils.essentials import Essentials

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

GDRIVE_API_KEY = os.getenv("GDRIVE_API_KEY")
GDRIVE_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:[\w\-]+\.)?(?:drive|docs)\.google\.com\/(?:(?:file\/u\/\d+\/d\/|file\/d\/|open\?id=|uc\?id=))([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)


def _extract_file_id(url: str) -> Optional[str]:
    match = GDRIVE_REGEX.search(url)
    return match.group(1) if match else None


@Friday.register_on_cmd(
    ["gdinfo", "gdrive"],
    cmd_help={
        "help": "Inspect Google Drive file details (name, size, direct download link).",
        "example": "gdrive https://drive.google.com/file/d/1abc.../view",
    },
    requires_input=True,
)
async def gdrive_info(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for Google Drive tools.")

    raw = m.user_input.strip()
    file_id = _extract_file_id(raw)
    if not file_id:
        return await m.handle_message("❌ Invalid Google Drive URL or File ID.")

    msg = await m.handle_message(f"🔍 Inspecting Google Drive file <code>{file_id}</code>...")

    try:
        # If API key is configured via env
        if GDRIVE_API_KEY:
            api_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,size,mimeType&key={GDRIVE_API_KEY}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(api_url)
            if res.status_code == 200:
                data = res.json()
                name = data.get("name", "Unknown")
                size = Essentials.humanbytes(int(data.get("size", 0))) if data.get("size") else "Unknown"
                mime = data.get("mimeType", "Unknown")
                direct_url = f"https://docs.google.com/uc?export=download&id={file_id}"
                report = (
                    "📁 <b>Google Drive File Details:</b>\n\n"
                    f"<b>• Name:</b> <code>{name}</code>\n"
                    f"<b>• Size:</b> <code>{size}</code>\n"
                    f"<b>• MIME:</b> <code>{mime}</code>\n"
                    f"<b>• Direct Link:</b> <a href='{direct_url}'>Download Stream</a>"
                )
                return await msg.edit_msg(report)

        # Direct HTTP headers inspection for shared files
        download_url = f"https://docs.google.com/uc?export=download&id={file_id}"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.head(download_url)
            if res.status_code != 200:
                res = await client.get(download_url, headers={"Range": "bytes=0-10"})

        headers = res.headers
        content_disp = headers.get("content-disposition", "")
        filename = "Unknown"
        if "filename=" in content_disp:
            parts = content_disp.split("filename=")
            filename = parts[1].strip('"').strip("'").split(";")[0]

        size_raw = headers.get("content-length")
        size = Essentials.humanbytes(int(size_raw)) if size_raw else "Dynamic / Unknown"

        report = (
            "📁 <b>Google Drive File Details:</b>\n\n"
            f"<b>• File ID:</b> <code>{file_id}</code>\n"
            f"<b>• Detected Name:</b> <code>{filename}</code>\n"
            f"<b>• Size:</b> <code>{size}</code>\n"
            f"<b>• Direct Stream:</b> <a href='{download_url}'>Click to Download</a>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Google Drive inspection error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["gddownload", "gdget"],
    cmd_help={
        "help": "Download a public Google Drive file directly and upload it to Telegram.",
        "example": "gddownload https://drive.google.com/file/d/1abc.../view",
    },
    requires_input=True,
)
async def gdrive_download(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    raw = m.user_input.strip()
    file_id = _extract_file_id(raw)
    if not file_id:
        return await m.handle_message("❌ Invalid Google Drive URL or File ID.")

    msg = await m.handle_message("⏳ Fetching file from Google Drive...")
    os.makedirs("temp/xtra_gdrive", exist_ok=True)
    temp_file = f"temp/xtra_gdrive/gd_{file_id}"

    download_url = f"https://docs.google.com/uc?export=download&id={file_id}"
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", download_url) as resp:
                if resp.status_code != 200:
                    return await msg.edit_msg(f"❌ Failed to stream file (HTTP {resp.status_code}). Ensure link is public.")

                content_disp = resp.headers.get("content-disposition", "")
                filename = f"file_{file_id}"
                if "filename=" in content_disp:
                    filename = content_disp.split("filename=")[1].strip('"').strip("'").split(";")[0]

                target_path = os.path.join("temp/xtra_gdrive", filename)
                with open(target_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)

        await msg.edit_msg("📤 Uploading Google Drive file to Telegram...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            target_path,
            caption=f"📁 <b>{filename}</b>\n<b>Size:</b> <code>{Essentials.humanbytes(os.path.getsize(target_path))}</code>",
            reply_to=m.id,
        )
        try:

            await msg.delete()

        except Exception:

            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Download failed: <code>{e}</code>")
    finally:
        for p in (temp_file, target_path if 'target_path' in locals() else None):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
