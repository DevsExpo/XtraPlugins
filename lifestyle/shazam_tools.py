# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN", "test")


@Friday.register_on_cmd(
    ["shazam", "whatsong", "identify"],
    cmd_help={
        "help": "Identify the song playing in a replied audio, video, or voice message.",
        "example": "shazam (replying to audio/video/voice)",
    },
    requires_reply=True,
)
async def identify_song(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for song identification.")

    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (
        rm.audio
        or rm.voice
        or rm.video
        or rm.video_note
        or (
            rm.file
            and rm.file.mime_type
            and (rm.file.mime_type.startswith("audio/") or rm.file.mime_type.startswith("video/"))
        )
    ):
        return await m.handle_message("❌ Please reply to an audio track, voice message, or video.")

    msg = await m.handle_message("🎧 Listening and identifying song fingerprint...")
    os.makedirs("temp/xtra_shazam", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_shazam/")

    if not download_path or not os.path.exists(download_path):
        return await msg.edit_msg("❌ Failed to download audio media.")

    try:
        # Use AudD API (supports public test token for short clips)
        api_url = "https://api.audd.io/"
        data = {
            "api_token": AUDD_API_TOKEN,
            "return": "apple_music,spotify",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(download_path, "rb") as f:
                files = {"file": (os.path.basename(download_path), f)}
                res = await client.post(api_url, data=data, files=files)

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ Recognition service returned HTTP {res.status_code}.")

        result_json = res.json()
        if result_json.get("status") != "success" or not result_json.get("result"):
            return await msg.edit_msg("🤷‍♂️ <b>No song match found.</b> Ensure audio is clear and try again.")

        song = result_json["result"]
        title = song.get("title", "Unknown Title")
        artist = song.get("artist", "Unknown Artist")
        album = song.get("album", "Unknown Album")
        release_date = song.get("release_date", "N/A")

        spotify = song.get("spotify", {}) or {}
        spotify_url = spotify.get("external_urls", {}).get("spotify", "")
        apple_music = song.get("apple_music", {}) or {}
        apple_url = apple_music.get("url", "")

        links = []
        if spotify_url:
            links.append(f"<a href='{spotify_url}'>Spotify</a>")
        if apple_url:
            links.append(f"<a href='{apple_url}'>Apple Music</a>")

        links_str = f"\n<b>• Links:</b> {' | '.join(links)}" if links else ""

        report = (
            "🎵 <b>Song Identified:</b>\n\n"
            f"<b>• Title:</b> <code>{title}</code>\n"
            f"<b>• Artist:</b> <code>{artist}</code>\n"
            f"<b>• Album:</b> <code>{album}</code>\n"
            f"<b>• Released:</b> <code>{release_date}</code>"
            f"{links_str}"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Song identification error: <code>{e}</code>")
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass
