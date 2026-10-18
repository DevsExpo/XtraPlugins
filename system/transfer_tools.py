# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import time
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.utils.essentials import Essentials

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _render_bar(percentage: float, length: int = 12) -> str:
    filled = int(round(length * (percentage / 100.0)))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


@Friday.register_on_cmd(
    ["geturl", "downloadurl", "fetchurl"],
    cmd_help={
        "help": "Download a file directly from any URL and send it to chat with a live progress bar.",
        "example": "geturl https://example.com/file.zip [custom_name.zip]",
    },
    requires_input=True,
)
async def download_from_url(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for transfer tools.")

    parts = m.user_input.strip().split()
    url = parts[0]
    custom_name = parts[1] if len(parts) > 1 else None

    msg = await m.handle_message("⚡ Connecting to source URL...")
    os.makedirs("temp/xtra_transfer", exist_ok=True)

    start_time = time.time()
    last_update = 0

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return await msg.edit_msg(f"❌ Server returned HTTP {resp.status_code}.")

                total_size = int(resp.headers.get("content-length", 0))

                # Determine file name
                if not custom_name:
                    content_disp = resp.headers.get("content-disposition", "")
                    if "filename=" in content_disp:
                        custom_name = content_disp.split("filename=")[1].strip('"').strip("'").split(";")[0]
                    else:
                        custom_name = url.split("?")[0].split("/")[-1] or f"download_{int(time.time())}.bin"

                out_path = os.path.join("temp/xtra_transfer", custom_name)
                downloaded = 0

                with open(out_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()

                        # Update progress bar every 3 seconds
                        if total_size > 0 and (now - last_update) >= 3.0:
                            pct = round(downloaded * 100.0 / total_size, 1)
                            speed = downloaded / (now - start_time) if (now - start_time) > 0 else 0
                            bar = _render_bar(pct)
                            status_text = (
                                f"📥 <b>Downloading:</b> <code>{custom_name}</code>\n"
                                f"<code>[{bar}] {pct}%</code>\n"
                                f"<b>• Size:</b> <code>{Essentials.humanbytes(downloaded)} / {Essentials.humanbytes(total_size)}</code>\n"
                                f"<b>• Speed:</b> <code>{Essentials.humanbytes(speed)}/s</code>"
                            )
                            try:
                                await msg.edit_msg(status_text)
                            except Exception:
                                pass
                            last_update = now

        file_size = Essentials.humanbytes(os.path.getsize(out_path))
        time_taken = round(time.time() - start_time, 2)
        await msg.edit_msg(f"📤 Download finished in <code>{time_taken}s</code>. Initializing Telegram upload...")

        upload_start = time.time()
        last_upload_edit = [0]

        async def _upload_progress(current, total):
            now = time.time()
            if (now - last_upload_edit[0]) >= 3.0 or current == total:
                pct = round(current * 100.0 / total, 1) if total else 0
                speed = current / (now - upload_start) if (now - upload_start) > 0 else 0
                bar = _render_bar(pct)
                eta_sec = int((total - current) / speed) if speed > 0 and total else 0
                eta = Essentials.get_readable_time(eta_sec)
                txt = (
                    f"📤 <b>Uploading:</b> <code>{custom_name}</code>\n"
                    f"<code>[{bar}] {pct}%</code>\n"
                    f"<b>• Transferred:</b> <code>{Essentials.humanbytes(current)} / {Essentials.humanbytes(total)}</code>\n"
                    f"<b>• Speed:</b> <code>{Essentials.humanbytes(speed)}/s</code>\n"
                    f"<b>• ETA:</b> <code>{eta}</code>"
                )
                try:
                    await msg.edit_msg(txt)
                except Exception:
                    pass
                last_upload_edit[0] = now

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_path,
            caption=(
                f"📁 <b>{custom_name}</b>\n"
                f"<b>• Size:</b> <code>{file_size}</code>\n"
                f"<b>• Download Time:</b> <code>{time_taken}s</code>"
            ),
            reply_to=m.id,
            progress_callback=_upload_progress,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Transfer error: <code>{e}</code>")
    finally:
        if "out_path" in locals() and os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["putfile", "tgup"],
    cmd_help={
        "help": "Upload a local server file to Telegram with a live visual progress bar.",
        "example": "putfile /path/to/file.zip",
    },
    requires_input=True,
)
async def upload_local_file(c: Client, m: Message):
    filepath = m.user_input.strip()
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        return await m.handle_message(f"❌ File not found: <code>{filepath}</code>")

    filename = os.path.basename(filepath)
    file_size = Essentials.humanbytes(os.path.getsize(filepath))
    msg = await m.handle_message(f"📤 Preparing upload for <code>{filename}</code> ({file_size})...")

    upload_start = time.time()
    last_upload_edit = [0]

    async def _upload_progress(current, total):
        now = time.time()
        if (now - last_upload_edit[0]) >= 3.0 or current == total:
            pct = round(current * 100.0 / total, 1) if total else 0
            speed = current / (now - upload_start) if (now - upload_start) > 0 else 0
            bar = _render_bar(pct)
            eta_sec = int((total - current) / speed) if speed > 0 and total else 0
            eta = Essentials.get_readable_time(eta_sec)
            txt = (
                f"📤 <b>Uploading:</b> <code>{filename}</code>\n"
                f"<code>[{bar}] {pct}%</code>\n"
                f"<b>• Transferred:</b> <code>{Essentials.humanbytes(current)} / {Essentials.humanbytes(total)}</code>\n"
                f"<b>• Speed:</b> <code>{Essentials.humanbytes(speed)}/s</code>\n"
                f"<b>• ETA:</b> <code>{eta}</code>"
            )
            try:
                await msg.edit_msg(txt)
            except Exception:
                pass
            last_upload_edit[0] = now

    try:
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            filepath,
            caption=f"📁 <code>{filename}</code> ({file_size})",
            reply_to=m.id,
            progress_callback=_upload_progress,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Upload failed: <code>{e}</code>")


@Friday.register_on_cmd(
    ["streamlink", "linkinfo"],
    cmd_help={
        "help": "Inspect a direct streaming or download link without downloading it.",
        "example": "streamlink https://example.com/video.mp4",
    },
    requires_input=True,
)
async def inspect_stream_link(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    url = m.user_input.strip()
    msg = await m.handle_message("🔍 Probing URL headers...")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.head(url)
            if res.status_code != 200:
                res = await client.get(url, headers={"Range": "bytes=0-10"})

        headers = res.headers
        content_type = headers.get("content-type", "Unknown")
        content_length = headers.get("content-length")
        size = Essentials.humanbytes(int(content_length)) if content_length else "Dynamic / Streaming"
        server = headers.get("server", "Hidden")
        accept_ranges = headers.get("accept-ranges", "None")

        report = (
            "🛰 <b>Link Stream Inspection:</b>\n\n"
            f"<b>• Content Type:</b> <code>{content_type}</code>\n"
            f"<b>• File Size:</b> <code>{size}</code>\n"
            f"<b>• Resumable Ranges:</b> <code>{accept_ranges}</code>\n"
            f"<b>• Server:</b> <code>{server}</code>\n"
            f"<b>• Status:</b> <code>HTTP {res.status_code}</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Probe error: <code>{e}</code>")
