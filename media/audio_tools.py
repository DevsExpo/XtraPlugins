# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import os
import shutil
import asyncio
import subprocess
from typing import Optional

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"


def _get_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    return "ffmpeg"


@Friday.register_on_cmd(
    ["cut", "audiocut", "mp3cut"],
    cmd_help={
        "help": "Trim or cut an audio or MP3 file by start and end timestamps (e.g. 00:30 01:45 or 30 105).",
        "example": "cut 00:15 01:30 (reply to audio)\ncut 30 90 (reply to audio)",
    },
    requires_reply=True,
)
async def audio_cut_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.audio or reply.voice or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to an audio or voice file to trim.")

    args = (m.user_input or "").strip().split()
    if len(args) < 2:
        return await m.handle_message("⚠️ <b>Usage:</b> <code>.cut &lt;start_time&gt; &lt;end_time&gt;</code>\nExample: <code>.cut 00:30 01:15</code>")

    start_t, end_t = args[0], args[1]
    msg = await m.handle_message(f"✂️ Trimming audio from <code>{start_t}</code> to <code>{end_t}</code>...")

    out_dir = os.path.join("temp", "audio_cut")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download audio media.")

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(out_dir, f"{base_name}_cut.mp3")

    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-ss", str(start_t),
        "-to", str(end_t),
        "-i", input_file,
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        output_file,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await proc.communicate()

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            return await msg.edit_msg("❌ Trimming failed. Please check timestamp format (e.g. <code>00:30 01:45</code>).")

        await msg.edit_msg("⬆️ Uploading trimmed audio...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            output_file,
            caption=f"✂️ <b>Trimmed Track:</b> <code>{start_t}</code> - <code>{end_t}</code>",
            reply_to=reply.id,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"❌ Error during trimming: <code>{e}</code>")
    finally:
        for f in [input_file, output_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["tag", "audiotag", "id3"],
    cmd_help={
        "help": "Edit ID3 tags of an audio track (title, artist, album, year).",
        "example": "tag -title \"My Song\" -artist \"Artist\" (reply to audio)",
    },
    requires_reply=True,
)
async def audio_tag_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.audio or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to an audio track to edit tags.")

    raw = (m.user_input or "").strip()
    if not raw:
        return await m.handle_message("⚠️ <b>Usage:</b> <code>.tag -title \"Title\" -artist \"Artist\" -album \"Album\"</code>")

    title = None
    artist = None
    album = None

    if "-title " in raw:
        parts = raw.split("-title ")
        title = parts[1].split("-artist ")[0].split("-album ")[0].strip().strip('"')
    if "-artist " in raw:
        parts = raw.split("-artist ")
        artist = parts[1].split("-title ")[0].split("-album ")[0].strip().strip('"')
    if "-album " in raw:
        parts = raw.split("-album ")
        album = parts[1].split("-title ")[0].split("-artist ")[0].strip().strip('"')

    msg = await m.handle_message("🏷 Updating ID3 metadata tags...")
    out_dir = os.path.join("temp", "audio_tag")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download audio media.")

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(out_dir, f"{base_name}_tagged.mp3")

    ffmpeg = _get_ffmpeg()
    cmd = [ffmpeg, "-y", "-i", input_file, "-codec", "copy"]
    if title:
        cmd.extend(["-metadata", f"title={title}"])
    if artist:
        cmd.extend(["-metadata", f"artist={artist}"])
    if album:
        cmd.extend(["-metadata", f"album={album}"])
    cmd.append(output_file)

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await proc.communicate()

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            return await msg.edit_msg("❌ Tagging failed.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            output_file,
            caption=f"🏷 <b>Updated Audio:</b>\n• Title: <code>{title or 'Unchanged'}</code>\n• Artist: <code>{artist or 'Unchanged'}</code>\n• Album: <code>{album or 'Unchanged'}</code>",
            reply_to=reply.id,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"❌ Error tagging audio: <code>{e}</code>")
    finally:
        for f in [input_file, output_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["tovoice", "voice"],
    cmd_help={
        "help": "Convert any replied video, audio, or music into a native Telegram voice note (Opus).",
        "example": "tovoice (reply to video or audio)",
    },
    requires_reply=True,
)
async def to_voice_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.audio or reply.video or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to an audio or video file to convert to a voice note.")

    msg = await m.handle_message("🎙 Converting media to Telegram voice note...")
    out_dir = os.path.join("temp", "voice_conv")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download media.")

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(out_dir, f"{base_name}.ogg")

    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-i", input_file,
        "-vn",
        "-c:a", "libopus",
        "-b:a", "64k",
        "-vbr", "on",
        output_file,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await proc.communicate()

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            return await msg.edit_msg("❌ Voice conversion failed.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            output_file,
            voice_note=True,
            reply_to=reply.id,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"❌ Error: <code>{e}</code>")
    finally:
        for f in [input_file, output_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["tovideo", "telescope", "videonote"],
    cmd_help={
        "help": "Convert a replied video into a circular Telegram video note (Telescope note).",
        "example": "tovideo (reply to short video clip)",
    },
    requires_reply=True,
)
async def to_videonote_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.video or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to a video to convert to a round video note.")

    msg = await m.handle_message("⭕ Converting video into circular telescope note...")
    out_dir = os.path.join("temp", "video_note")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download video.")

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(out_dir, f"{base_name}_round.mp4")

    # Crop to 1:1 aspect ratio, max 480x480, max 60 seconds
    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-t", "60",
        "-i", input_file,
        "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=480:480",
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        output_file,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await proc.communicate()

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            return await msg.edit_msg("❌ Video note conversion failed.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            output_file,
            video_note=True,
            reply_to=reply.id,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"❌ Error: <code>{e}</code>")
    finally:
        for f in [input_file, output_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
