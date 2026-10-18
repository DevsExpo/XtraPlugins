# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import re
import time
import asyncio
from typing import Optional, Dict, Any

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import yt_dlp

    HAS_YTDL = True
except ImportError:
    HAS_YTDL = False

try:
    import imageio_ffmpeg

    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    import shutil

    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "Live / Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_count(num: Optional[int]) -> str:
    if not num:
        return "0"
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)


def _get_ffmpeg_cmd() -> Optional[str]:
    import shutil

    path = shutil.which("ffmpeg")
    if path:
        return path
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    return None


def _parse_time_str(val: str) -> Optional[int]:
    """Parse time string like 01:30 or 90 into seconds."""
    if not val:
        return None
    val = val.strip()
    if val.isdigit():
        return int(val)
    parts = val.split(":")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return None


async def _get_ytdl_auth_opts() -> Dict[str, Any]:
    """Configure anti-bot client fallback, cookies, and account/PO tokens to eliminate YouTube bot detection."""
    opts: Dict[str, Any] = {}

    # 1. Multi-player client fallback: bypasses 'Sign in to confirm you are not a bot' on datacenter IPs
    extractor_args = opts.setdefault("extractor_args", {})
    yt_args = extractor_args.setdefault("youtube", {})
    yt_args["player_client"] = ["ios", "android", "mweb", "web"]

    # 2. Check for cookie file on disk or database
    cookie_paths = [
        os.path.join("cache", "yt_cookies.txt"),
        os.path.join("temp", "yt_cookies.txt"),
        "cookies.txt",
    ]
    found_cookie = None
    for cp in cookie_paths:
        if os.path.exists(cp) and os.path.getsize(cp) > 0:
            found_cookie = cp
            break

    # Check database for saved cookies / tokens
    if hasattr(Friday, "db") and Friday.db is not None:
        try:
            doc = await Friday.db["YTDL_AUTH"].find_one({"_id": "youtube_config"})
            if doc:
                if not found_cookie and doc.get("cookies_text"):
                    c_dir = os.path.join("cache")
                    os.makedirs(c_dir, exist_ok=True)
                    target_cp = os.path.join(c_dir, "yt_cookies.txt")
                    with open(target_cp, "w", encoding="utf-8") as f:
                        f.write(doc["cookies_text"])
                    found_cookie = target_cp

                if doc.get("po_token"):
                    yt_args["po_token"] = [f"web+{doc['po_token']}"]
                if doc.get("oauth_token"):
                    yt_args["oauth_token"] = [doc["oauth_token"]]
        except Exception:
            pass

    if found_cookie:
        opts["cookiefile"] = found_cookie

    # Environment overrides
    env_po = os.environ.get("YT_PO_TOKEN")
    if env_po:
        yt_args["po_token"] = [f"web+{env_po}"]

    env_cookie = os.environ.get("YT_COOKIES_PATH")
    if env_cookie and os.path.exists(env_cookie):
        opts["cookiefile"] = env_cookie

    return opts


def _parse_ytdl_flags(raw_input: str) -> Dict[str, Any]:
    """Parse media flags: quality, format, bitrate, document mode, trimming, and subs."""
    flags = {
        "quality": "720",
        "audio_only": False,
        "audio_format": "mp3",
        "audio_bitrate": "320",
        "as_document": False,
        "send_thumb": True,
        "thumb_separate": False,
        "subtitles": False,
        "start_time": None,
        "end_time": None,
        "custom_title": None,
        "info_only": False,
        "clean_query": "",
    }

    tokens = raw_input.split()
    query_parts = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        tl = token.lower()

        # Quality flags
        if tl in ("-4k", "-2160p", "-2160"):
            flags["quality"] = "2160"
        elif tl in ("-2k", "-1440p", "-1440"):
            flags["quality"] = "1440"
        elif tl in ("-1080p", "-1080"):
            flags["quality"] = "1080"
        elif tl in ("-720p", "-720"):
            flags["quality"] = "720"
        elif tl in ("-480p", "-480"):
            flags["quality"] = "480"
        elif tl in ("-360p", "-360"):
            flags["quality"] = "360"
        elif tl in ("-240p", "-240"):
            flags["quality"] = "240"
        elif tl in ("-144p", "-144"):
            flags["quality"] = "144"
        elif tl in ("-best", "-max"):
            flags["quality"] = "max"
        elif tl in ("-worst", "-low"):
            flags["quality"] = "worst"

        # Audio flags
        elif tl in ("-a", "-audio"):
            flags["audio_only"] = True
        elif tl in ("-mp3", "-m4a", "-flac", "-opus", "-wav", "-aac"):
            flags["audio_only"] = True
            flags["audio_format"] = tl.lstrip("-")
        elif tl in ("-320k", "-320"):
            flags["audio_bitrate"] = "320"
        elif tl in ("-256k", "-256"):
            flags["audio_bitrate"] = "256"
        elif tl in ("-192k", "-192"):
            flags["audio_bitrate"] = "192"
        elif tl in ("-128k", "-128"):
            flags["audio_bitrate"] = "128"
        elif tl == "-kbps" and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            i += 1
            flags["audio_bitrate"] = tokens[i]

        # Sending mode
        elif tl in ("-doc", "-d", "-file"):
            flags["as_document"] = True
        elif tl in ("-thumb", "-t"):
            flags["thumb_separate"] = True
        elif tl in ("-nothumb", "-not"):
            flags["send_thumb"] = False

        # Subtitles
        elif tl in ("-subs", "-sub", "-subtitles"):
            flags["subtitles"] = True

        # Info inspection
        elif tl in ("-info", "-i"):
            flags["info_only"] = True

        # Clipping / Trimming: -ss <time> -to <time>
        elif tl == "-ss" and i + 1 < len(tokens):
            i += 1
            flags["start_time"] = _parse_time_str(tokens[i])
        elif tl == "-to" and i + 1 < len(tokens):
            i += 1
            flags["end_time"] = _parse_time_str(tokens[i])

        # Custom Title
        elif tl == "-title" and i + 1 < len(tokens):
            i += 1
            flags["custom_title"] = tokens[i]

        else:
            query_parts.append(token)

        i += 1

    flags["clean_query"] = " ".join(query_parts).strip()
    return flags


@Friday.register_on_cmd(
    ["ytdl", "ytvideo", "ytv", "ig", "reel", "tiktok", "tt", "twitter", "tw", "reddit", "pinterest", "fb"],
    cmd_help={
        "help": "Universal Social Media & Video Downloader: YouTube, Instagram Reels, TikTok, Twitter/X, Reddit, Pinterest, Facebook with advanced flags.",
        "example": "dl https://youtu.be/... -1080p -doc\ndl https://instagram.com/reel/...\nytdl lofi hip hop -audio -mp3 -320k\nytdl https://youtu.be/... -ss 00:30 -to 01:15",
    },
    requires_input=True,
)
async def youtube_download_video(c: Client, m: Message):
    if not HAS_YTDL:
        return await m.handle_message(
            "❌ <code>yt-dlp</code> is required. Install via <code>pip install yt-dlp</code>."
        )

    flags = _parse_ytdl_flags(m.user_input)
    query = flags["clean_query"]
    if not query:
        return await m.handle_message(
            "❌ Please provide a media URL (YouTube, Instagram, TikTok, X, Reddit, etc.) or search query."
        )

    # Redirect to audio extraction if -audio / -a flag provided
    if flags["audio_only"]:
        return await _download_audio_worker(c, m, flags)

    quality = flags["quality"]
    msg = await m.handle_message(f"🔍 Searching & extracting video (Quality: <b>{quality}p</b>)...")
    out_dir = os.path.join("temp", "xtra_ytdl")
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl = os.path.join(out_dir, "%(id)s.%(ext)s")

    if quality == "max":
        format_spec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    elif quality == "worst":
        format_spec = "worstvideo+worstaudio/worst"
    else:
        format_spec = f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]/best"

    ydl_opts: Dict[str, Any] = {
        "format": format_spec,
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writethumbnail": flags["send_thumb"],
    }

    # Anti-bot bypass & account token options
    auth_opts = await _get_ytdl_auth_opts()
    ydl_opts.update(auth_opts)

    # Subtitles support
    if flags["subtitles"]:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = ["en", "auto"]

    # Clipping / Trimming range
    if flags["start_time"] is not None or flags["end_time"] is not None:
        s = flags["start_time"] or 0
        e = flags["end_time"] or float("inf")
        try:
            ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(s, e)])
        except Exception:
            pass

    ffmpeg_bin = _get_ffmpeg_cmd()
    if ffmpeg_bin:
        ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin) if os.path.isfile(ffmpeg_bin) else ffmpeg_bin

    try:
        loop = asyncio.get_running_loop()

        def _extract_and_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_target = (
                    query if query.startswith("http://") or query.startswith("https://") else f"ytsearch1:{query}"
                )
                info = ydl.extract_info(search_target, download=not flags["info_only"])
                if "entries" in info and info["entries"]:
                    return info["entries"][0]
                return info

        await msg.edit_msg(f"⬇️ Downloading media: <code>{query}</code>...")
        entry = await loop.run_in_executor(None, _extract_and_download)

        vid_id = entry.get("id")
        title = flags["custom_title"] or entry.get("title", "Video")
        duration = int(entry.get("duration") or 0)
        channel = entry.get("uploader") or entry.get("channel", "Media")
        web_url = entry.get("webpage_url") or f"https://youtu.be/{vid_id}"

        if flags["info_only"]:
            views = _format_count(entry.get("view_count"))
            likes = _format_count(entry.get("like_count"))
            return await msg.edit_msg(
                f"ℹ️ <b>Media Info:</b> <a href='{web_url}'>{title}</a>\n\n"
                f"• <b>Duration:</b> <code>{_format_duration(duration)}</code>\n"
                f"• <b>Uploader:</b> <code>{channel}</code>\n"
                f"• <b>Views:</b> <code>{views}</code> | 👍 <b>Likes:</b> <code>{likes}</code>"
            )

        # Locate downloaded video file
        video_file = None
        thumb_file = None
        for fn in os.listdir(out_dir):
            if fn.startswith(vid_id):
                fp = os.path.join(out_dir, fn)
                if fn.endswith((".mp4", ".mkv", ".webm", ".mov")):
                    video_file = fp
                elif fn.endswith((".jpg", ".jpeg", ".webp", ".png")):
                    thumb_file = fp

        if not video_file or not os.path.exists(video_file):
            return await msg.edit_msg("❌ Video download failed: file not found on disk.")

        file_size_mb = os.path.getsize(video_file) / (1024 * 1024)
        if file_size_mb > 2000:
            return await msg.edit_msg(f"❌ File size exceeds Telegram 2GB limit ({file_size_mb:.1f} MB).")

        await msg.edit_msg(f"⬆️ Uploading <b>{title}</b> ({file_size_mb:.1f} MB)...")

        platform_badge = "🎬 Video"
        low = web_url.lower()
        if "instagram.com" in low:
            platform_badge = "📸 Instagram Reel/Post"
        elif "tiktok.com" in low:
            platform_badge = "🎵 TikTok Clip"
        elif "x.com" in low or "twitter.com" in low:
            platform_badge = "🐦 Twitter/X Media"
        elif "reddit.com" in low:
            platform_badge = "🤖 Reddit Video"
        elif "pinterest.com" in low:
            platform_badge = "📌 Pinterest Pin"
        elif "facebook.com" in low or "fb.watch" in low:
            platform_badge = "📘 Facebook Video"
        elif "youtube.com" in low or "youtu.be" in low:
            platform_badge = "▶️ YouTube Video"

        caption = (
            f"<b>{platform_badge}:</b> <a href='{web_url}'>{title}</a>\n"
            f"⏱ <b>Duration:</b> <code>{_format_duration(duration)}</code> | 👤 <b>Author:</b> <code>{channel}</code>"
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)

        if flags["thumb_separate"] and thumb_file and os.path.exists(thumb_file):
            await c.send_file(target_chat, thumb_file, caption=f"🖼️ Thumbnail for: <b>{title}</b>", reply_to=m.id)

        # Uses unified flood-wait safe progress_msg
        await c.send_file(
            target_chat,
            video_file,
            caption=caption,
            thumb=thumb_file if (flags["send_thumb"] and thumb_file and os.path.exists(thumb_file)) else None,
            supports_streaming=not flags["as_document"],
            force_document=flags["as_document"],
            reply_to=m.id,
            progress_msg=msg,
        )

        await msg.delete()

    except Exception as e:
        await msg.edit_msg(f"❌ Video error: <code>{e}</code>")
    finally:
        try:
            if "vid_id" in locals():
                for fn in os.listdir(out_dir):
                    if fn.startswith(vid_id):
                        try:
                            os.remove(os.path.join(out_dir, fn))
                        except Exception:
                            pass
        except Exception:
            pass


async def _download_audio_worker(c: Client, m: Message, flags: Dict[str, Any]):
    query = flags["clean_query"]
    msg = await m.handle_message(
        f"🎵 Searching audio <b>{query}</b> ({flags['audio_format'].upper()} @ {flags['audio_bitrate']}kbps)..."
    )
    out_dir = os.path.join("temp", "xtra_ytdl")
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl = os.path.join(out_dir, "%(id)s.%(ext)s")

    ffmpeg_bin = _get_ffmpeg_cmd()
    postprocessors = (
        [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": flags["audio_format"],
                "preferredquality": flags["audio_bitrate"],
            }
        ]
        if ffmpeg_bin
        else []
    )

    ydl_opts: Dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writethumbnail": flags["send_thumb"],
        "postprocessors": postprocessors,
    }

    # Anti-bot bypass & account token options
    auth_opts = await _get_ytdl_auth_opts()
    ydl_opts.update(auth_opts)

    if ffmpeg_bin:
        ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin) if os.path.isfile(ffmpeg_bin) else ffmpeg_bin

    try:
        loop = asyncio.get_running_loop()

        def _extract_and_download_audio():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_target = (
                    query if query.startswith("http://") or query.startswith("https://") else f"ytsearch1:{query}"
                )
                info = ydl.extract_info(search_target, download=True)
                if "entries" in info and info["entries"]:
                    return info["entries"][0]
                return info

        await msg.edit_msg(f"⬇️ Downloading audio track: <code>{query}</code>...")
        entry = await loop.run_in_executor(None, _extract_and_download_audio)

        vid_id = entry.get("id")
        title = flags["custom_title"] or entry.get("title", "Audio Track")
        duration = int(entry.get("duration") or 0)
        performer = entry.get("artist") or entry.get("uploader") or entry.get("channel", "Unknown Artist")
        web_url = entry.get("webpage_url") or f"https://youtu.be/{vid_id}"

        audio_file = None
        thumb_file = None
        for fn in os.listdir(out_dir):
            if fn.startswith(vid_id):
                fp = os.path.join(out_dir, fn)
                if fn.endswith((".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav", ".aac")):
                    audio_file = fp
                elif fn.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    thumb_file = fp

        if not audio_file or not os.path.exists(audio_file):
            return await msg.edit_msg("❌ Audio extraction failed: file not found on disk.")

        file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
        await msg.edit_msg(f"⬆️ Uploading <b>{title}</b> ({file_size_mb:.1f} MB)...")

        caption = (
            f"🎧 <b><a href='{web_url}'>{title}</a></b>\n"
            f"👤 <b>Artist:</b> <code>{performer}</code> | ⏱ <b>Duration:</b> <code>{_format_duration(duration)}</code> | 🎼 <code>{flags['audio_format'].upper()} {flags['audio_bitrate']}k</code>"
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            audio_file,
            caption=caption,
            thumb=thumb_file if (flags["send_thumb"] and thumb_file and os.path.exists(thumb_file)) else None,
            force_document=flags["as_document"],
            reply_to=m.id,
            progress_msg=msg,
        )

        await msg.delete()

    except Exception as e:
        await msg.edit_msg(f"❌ Song error: <code>{e}</code>")
    finally:
        try:
            if "vid_id" in locals():
                for fn in os.listdir(out_dir):
                    if fn.startswith(vid_id):
                        try:
                            os.remove(os.path.join(out_dir, fn))
                        except Exception:
                            pass
        except Exception:
            pass


@Friday.register_on_cmd(
    ["ytmp3", "ytaudio", "song", "music"],
    cmd_help={
        "help": "Download high bitrate audio / song with embedded tags, thumbnail, and custom bitrate/format flags.",
        "example": "ytmp3 https://youtu.be/... -flac\nsong Bohemian Rhapsody -320k -doc",
    },
    requires_input=True,
)
async def youtube_download_audio(c: Client, m: Message):
    if not HAS_YTDL:
        return await m.handle_message(
            "❌ <code>yt-dlp</code> is required. Install via <code>pip install yt-dlp</code>."
        )

    flags = _parse_ytdl_flags(m.user_input)
    flags["audio_only"] = True
    if not flags["clean_query"]:
        return await m.handle_message("❌ Please provide song name or YouTube link.")

    await _download_audio_worker(c, m, flags)


@Friday.register_on_cmd(
    ["setyttoken", "yttoken"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Set Proof-of-Origin (PO) Token or check YouTube authentication to eliminate bot-detection errors.",
        "example": "setyttoken <po_token>",
    },
)
async def set_yt_token_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    token = (m.user_input or "").strip()

    auth_col = Friday.db.make_collection("YTDL_AUTH")
    if not token:
        doc = await auth_col.find_one({"_id": "youtube_config"}) or {}
        curr_po = doc.get("po_token", "None")
        has_cookies = bool(doc.get("cookies_text") or os.path.exists("cache/yt_cookies.txt"))
        cookie_status = "🟢 Active" if has_cookies else "⚪ Not set"
        po_status = f"🟢 <code>{curr_po[:12]}...</code>" if curr_po != "None" else "⚪ Not set"
        return await msg.edit_msg(
            f"🛡️ <b>YouTube Authentication & Anti-Bot Status:</b>\n\n"
            f"• <b>Cookies:</b> {cookie_status}\n"
            f"• <b>PO Token:</b> {po_status}\n"
            f"• <b>Anti-Bot Bypass:</b> 🟢 Multi-Client Strategy (iOS, Android, Web)\n\n"
            f"<i>To configure:</i>\n"
            f"• <code>{Friday.user_command_handler}setyttoken &lt;po_token&gt;</code>\n"
            f"• Reply to a <code>cookies.txt</code> file with <code>{Friday.user_command_handler}setytcookies</code>"
        )

    await auth_col.update_one(
        {"_id": "youtube_config"},
        {"$set": {"po_token": token, "updated_at": time.time()}},
        upsert=True,
    )
    return await msg.edit_msg(
        "✅ <b>YouTube PO Token Saved!</b> Anti-bot checks will now authenticate with this token."
    )


@Friday.register_on_cmd(
    ["setytcookies", "ytcookies"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Set YouTube account cookies by replying to a cookies.txt file or passing cookie text.",
        "example": "setytcookies (in reply to cookies.txt)",
    },
)
async def set_yt_cookies_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    auth_col = Friday.db.make_collection("YTDL_AUTH")

    content = None
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if rm and getattr(rm, "file", None):
        temp_dir = os.path.join("temp")
        os.makedirs(temp_dir, exist_ok=True)
        downloaded = await c.download_media(rm, file=os.path.join(temp_dir, "incoming_cookies.txt"))
        if downloaded and os.path.exists(downloaded):
            with open(downloaded, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            try:
                os.remove(downloaded)
            except Exception:
                pass
    elif m.user_input and len(m.user_input.strip()) > 20:
        content = m.user_input.strip()

    if not content:
        return await msg.edit_msg(
            "⚠️ <b>Cookies Input Required:</b>\n"
            "Please reply to a <code>cookies.txt</code> document exported from your browser, or paste cookie text."
        )

    c_dir = os.path.join("cache")
    os.makedirs(c_dir, exist_ok=True)
    target_cp = os.path.join(c_dir, "yt_cookies.txt")
    with open(target_cp, "w", encoding="utf-8") as f:
        f.write(content)

    await auth_col.update_one(
        {"_id": "youtube_config"},
        {"$set": {"cookies_text": content, "updated_at": time.time()}},
        upsert=True,
    )
    return await msg.edit_msg(
        "✅ <b>YouTube Account Cookies Saved!</b> Age-restricted and member-only content is now unlocked."
    )


@Friday.register_on_cmd(
    ["rmyttoken", "clearyttoken"],
    bot_mode_unsupported=True,
    cmd_help={
        "help": "Remove saved YouTube account tokens and cookies.",
        "example": "rmyttoken",
    },
)
async def rm_yt_token_cmd(c: Client, m: Message):
    msg = await m.handle_message("PROCESSING")
    auth_col = Friday.db.make_collection("YTDL_AUTH")
    await auth_col.delete_one({"_id": "youtube_config"})
    for cp in ["cache/yt_cookies.txt", "temp/yt_cookies.txt"]:
        if os.path.exists(cp):
            try:
                os.remove(cp)
            except Exception:
                pass
    return await msg.edit_msg("🗑️ <b>YouTube Authentication Reset:</b> Tokens and cookies purged.")


@Friday.register_on_cmd(
    ["ytsearch", "yts"],
    cmd_help={
        "help": "Search YouTube for videos with metadata, view count, duration, and download commands.",
        "example": "ytsearch lofi beats to study to\nyts interstellar soundtrack",
    },
    requires_input=True,
)
async def youtube_search_list(c: Client, m: Message):
    if not HAS_YTDL:
        return await m.handle_message("❌ <code>yt-dlp</code> is required.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🔍 Searching YouTube for <b>{query}</b>...")

    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }
    auth_opts = await _get_ytdl_auth_opts()
    ydl_opts.update(auth_opts)

    try:
        loop = asyncio.get_running_loop()

        def _search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(f"ytsearch5:{query}", download=False)

        res = await loop.run_in_executor(None, _search)
        entries = res.get("entries", []) if res else []

        if not entries:
            return await msg.edit_msg(f"🤷‍♂️ No YouTube results found for <code>{query}</code>.")

        cards = []
        for i, item in enumerate(entries[:5], 1):
            vid_id = item.get("id")
            title = item.get("title", "Untitled")
            duration = _format_duration(item.get("duration"))
            channel = item.get("uploader") or item.get("channel", "YouTube")
            views = _format_count(item.get("view_count"))
            url = f"https://youtu.be/{vid_id}"

            card = (
                f"<b>{i}. <a href='{url}'>{title}</a></b>\n"
                f"   ⏱ <code>{duration}</code> | 👁 <code>{views} views</code> | 👤 <code>{channel}</code>\n"
                f"   <i>Download:</i> <code>.ytdl {vid_id}</code> | <code>.ytmp3 {vid_id}</code>"
            )
            cards.append(card)

        report = (
            f"🎬 <b>YouTube Search Results for:</b> <code>{query}</code>\n\n"
            + "\n\n".join(cards)
            + "\n\n💡 <i>Tip: Copy any command above to download instantly!</i>"
        )

        token = str(int(time.time() * 1000))[-8:]
        _yts_cache[token] = entries[:5]

        if "-basic" not in m.user_args and "-text" not in m.user_args:
            try:
                from Main.utils.inline_helper import send_inline_widget

                if await send_inline_widget(c, m, f"yts:{token}"):
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    return
            except Exception:
                pass

        await msg.edit_msg(report, disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_msg(f"❌ YouTube search error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["ytinfo"],
    cmd_help={
        "help": "Display technical video specifications, available formats, view counts, and channel metadata.",
        "example": "ytinfo https://youtu.be/...",
    },
    requires_input=True,
)
async def youtube_info_inspect(c: Client, m: Message):
    if not HAS_YTDL:
        return await m.handle_message("❌ <code>yt-dlp</code> is required.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🔍 Fetching technical metadata for <b>{query}</b>...")

    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    auth_opts = await _get_ytdl_auth_opts()
    ydl_opts.update(auth_opts)

    try:
        loop = asyncio.get_running_loop()

        def _get_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(query, download=False)

        info = await loop.run_in_executor(None, _get_info)

        title = info.get("title", "Untitled")
        vid_id = info.get("id")
        duration = _format_duration(info.get("duration"))
        views = _format_count(info.get("view_count"))
        likes = _format_count(info.get("like_count"))
        channel = info.get("uploader") or info.get("channel", "Unknown")
        upload_date = info.get("upload_date") or "Unknown"
        if len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        formats = info.get("formats", [])
        resolutions = sorted(list({f.get("height") for f in formats if f.get("height")}), reverse=True)
        res_str = ", ".join([f"{r}p" for r in resolutions[:6]]) if resolutions else "Standard"

        desc = (info.get("description") or "").strip()
        desc_snippet = f'<i>"{desc[:200]}..."</i>' if desc else "<i>No description</i>"

        report = (
            f"ℹ️ <b>YouTube Video Analysis:</b>\n\n"
            f"📌 <b>Title:</b> <code>{title}</code>\n"
            f"🆔 <b>Video ID:</b> <code>{vid_id}</code>\n"
            f"👤 <b>Channel:</b> <code>{channel}</code>\n"
            f"⏱ <b>Duration:</b> <code>{duration}</code>\n"
            f"👁 <b>Views:</b> <code>{views}</code> | 👍 <b>Likes:</b> <code>{likes}</code>\n"
            f"📅 <b>Uploaded:</b> <code>{upload_date}</code>\n"
            f"📺 <b>Resolutions:</b> <code>{res_str}</code>\n\n"
            f"<b>Description:</b>\n{desc_snippet}"
        )

        await msg.edit_msg(report, disable_web_page_preview=True)

    except Exception as e:
        await msg.edit_msg(f"❌ YouTube info error: <code>{e}</code>")


_yts_cache = {}

if getattr(Friday, "bot", None):
    import re
    from telethon import custom
    from Main.utils.custom_filters import filters

    @Friday.bot.on_inline_query(filters.regex(r"^yts:(\w+)"))
    async def yts_inline_query_handler(c, iq):
        m = re.match(r"^yts:(\w+)", iq.text)
        token = m.group(1) if m else ""
        entries = _yts_cache.get(token, [])
        if not entries:
            return

        builder = iq.builder
        results = []
        for it in entries:
            vid_id = it.get("id")
            title = it.get("title", "Untitled")
            duration = _format_duration(it.get("duration"))
            channel = it.get("uploader") or it.get("channel", "YouTube")
            views = _format_count(it.get("view_count"))
            url = f"https://youtu.be/{vid_id}"

            text = (
                f"🎬 <b><a href='{url}'>{title}</a></b>\n\n"
                f"⏱ <b>Duration:</b> <code>{duration}</code>\n"
                f"👤 <b>Channel:</b> <code>{channel}</code>\n"
                f"👁 <b>Views:</b> <code>{views}</code>\n\n"
                f"<i>• Download Audio:</i> <code>.ytmp3 {vid_id}</code>\n"
                f"<i>• Download Video:</i> <code>.ytdl {vid_id}</code>"
            )

            buttons = [
                [
                    custom.Button.url("🎬 Open YouTube", url),
                    custom.Button.inline("ℹ️ Download Hint", f"yt_hint:{vid_id}".encode("utf-8")),
                ]
            ]

            res = builder.article(
                title=title,
                description=f"⏱ {duration} | 👤 {channel} | 👁 {views} views",
                text=text,
                buttons=buttons,
                parse_mode="html",
            )
            results.append(res)

        await iq.answer(results, cache_time=0)

    @Friday.bot.on_callback_query(filters.regex(r"^yt_hint:(\w+)"))
    async def yt_hint_callback_handler(c, cq):
        m = re.match(r"^yt_hint:(\w+)", cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data))
        vid_id = m.group(1) if m else ""
        await cq.answer(f"🎵 Run .ytmp3 {vid_id} for audio or .ytdl {vid_id} for video!", alert=True)
