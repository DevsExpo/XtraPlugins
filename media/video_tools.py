# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import json
import shutil
import asyncio
from typing import Optional, Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.utils.essentials import Essentials
from Main.utils.file_utils import FileHelpers

# Check if ffmpeg is available
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None


def _check_ffmpeg():
    if not FFMPEG_AVAILABLE:
        raise RuntimeError(
            "<b>ffmpeg is not installed on this host.</b>\n"
            "Please install ffmpeg (e.g. <code>apt install ffmpeg</code> on Linux or add ffmpeg to PATH on Windows)."
        )


async def _run_command_async(cmd: list) -> Tuple[int, str, str]:
    """Execute subprocess asynchronously without blocking the event loop."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def _download_replied_video(m: Message) -> Tuple[Optional[str], Optional[str]]:
    """Helper to download replied video or document video."""
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (
        rm.video or rm.video_note or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("video/"))
    ):
        return None, None
    os.makedirs("temp/xtra_videos", exist_ok=True)
    file_path = await rm.download_media("temp/xtra_videos/")
    return file_path, "temp/xtra_videos"


@Friday.register_on_cmd(
    ["vinfo", "mediainfo"],
    cmd_help={
        "help": "Get detailed media information of replied video or audio file.",
        "example": "vinfo (replying to video/audio)",
    },
    requires_reply=True,
)
async def video_info(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ Please reply to a video, audio, or media file.")

    msg = await m.handle_message("🔍 Analyzing media metadata...")
    os.makedirs("temp/xtra_videos", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_videos/")

    try:
        file_size = Essentials.humanbytes(os.path.getsize(download_path))
        ext = os.path.splitext(download_path)[1]
        mime = rm.file.mime_type or "unknown"

        # Try extracting via ffprobe if available
        if FFPROBE_AVAILABLE:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                download_path,
            ]
            code, stdout, _ = await _run_command_async(cmd)
            if code == 0 and stdout:
                data = json.loads(stdout)
                fmt = data.get("format", {})
                duration = round(float(fmt.get("duration", 0)), 2)
                bitrate = Essentials.humanbytes(int(fmt.get("bit_rate", 0))) + "/s" if fmt.get("bit_rate") else "N/A"

                video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
                audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]

                res = f"{video_streams[0].get('width')}x{video_streams[0].get('height')}" if video_streams else "N/A"
                fps = video_streams[0].get("r_frame_rate", "N/A") if video_streams else "N/A"
                vcodec = video_streams[0].get("codec_name", "N/A") if video_streams else "None"
                acodec = audio_streams[0].get("codec_name", "N/A") if audio_streams else "None"

                report = (
                    "<b>🎬 Media Information</b>\n"
                    f"<b>• File:</b> <code>{os.path.basename(download_path)}</code>\n"
                    f"<b>• Size:</b> <code>{file_size}</code>\n"
                    f"<b>• MIME:</b> <code>{mime}</code>\n"
                    f"<b>• Duration:</b> <code>{duration}s</code>\n"
                    f"<b>• Resolution:</b> <code>{res}</code>\n"
                    f"<b>• Video Codec:</b> <code>{vcodec}</code> (FPS: <code>{fps}</code>)\n"
                    f"<b>• Audio Codec:</b> <code>{acodec}</code>\n"
                    f"<b>• Bitrate:</b> <code>{bitrate}</code>"
                )
                return await msg.edit_msg(report)

        # Fallback to hachoir / tinytag or file attributes
        fh = FileHelpers(download_path, client=c)
        dur, w, h = await fh._get_metadata(is_audio=False)

        report = (
            "<b>🎬 Media Information (Basic)</b>\n"
            f"<b>• File:</b> <code>{os.path.basename(download_path)}</code>\n"
            f"<b>• Size:</b> <code>{file_size}</code>\n"
            f"<b>• MIME:</b> <code>{mime}</code>\n"
            f"<b>• Duration:</b> <code>{dur}s</code>\n"
            f"<b>• Dimensions:</b> <code>{w}x{h}</code>\n"
            f"<b>• Extension:</b> <code>{ext}</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to extract media info: <code>{e}</code>")
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["vtrim"],
    cmd_help={
        "help": "Trim a video segment given start and end timestamps (e.g. 00:05 00:20 or 5 20).",
        "example": "vtrim 00:05 00:20 (replying to video)",
    },
    requires_reply=True,
    requires_input=True,
)
async def video_trim(c: Client, m: Message):
    try:
        _check_ffmpeg()
    except RuntimeError as err:
        return await m.handle_message(str(err))

    msg = await m.handle_message("⏳ Downloading video for trimming...")
    args = m.user_input.split()
    if len(args) < 2:
        return await msg.edit_msg("❌ Please specify start and end time. Example: <code>.vtrim 00:05 00:20</code>")

    start_pos = args[0]
    end_pos = args[1]

    file_path, _ = await _download_replied_video(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid video file.")

    out_path = f"temp/xtra_videos/trimmed_{os.path.basename(file_path)}"
    try:
        await msg.edit_msg(f"✂️ Trimming video from <code>{start_pos}</code> to <code>{end_pos}</code>...")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_pos),
            "-to",
            str(end_pos),
            "-i",
            file_path,
            "-c",
            "copy",
            out_path,
        ]
        code, stdout, stderr = await _run_command_async(cmd)
        if code != 0 or not os.path.exists(out_path):
            # Fallback with re-encoding if stream copy fails
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_pos),
                "-to",
                str(end_pos),
                "-i",
                file_path,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                out_path,
            ]
            code, stdout, stderr = await _run_command_async(cmd)
            if code != 0 or not os.path.exists(out_path):
                return await msg.edit_msg(f"❌ Trimming failed:\n<code>{stderr[-300:]}</code>")

        await msg.edit_msg("📤 Uploading trimmed video...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_path,
            caption=f"✂️ <b>Trimmed:</b> <code>{start_pos}</code> - <code>{end_pos}</code>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Error during trimming: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["vaudio", "vmp3"],
    cmd_help={
        "help": "Extract the audio track from a video as an MP3 file.",
        "example": "vaudio (replying to video)",
    },
    requires_reply=True,
)
async def video_extract_audio(c: Client, m: Message):
    try:
        _check_ffmpeg()
    except RuntimeError as err:
        return await m.handle_message(str(err))

    msg = await m.handle_message("⏳ Downloading video to extract audio...")
    file_path, _ = await _download_replied_video(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid video file.")

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    out_path = f"temp/xtra_videos/{base_name}.mp3"

    try:
        await msg.edit_msg("🎵 Extracting audio stream to MP3...")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            file_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            out_path,
        ]
        code, stdout, stderr = await _run_command_async(cmd)
        if code != 0 or not os.path.exists(out_path):
            return await msg.edit_msg(f"❌ Audio extraction failed:\n<code>{stderr[-300:]}</code>")

        await msg.edit_msg("📤 Uploading extracted MP3...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_path,
            caption=f"🎵 <b>Extracted Audio:</b> <code>{base_name}.mp3</code>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Error: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["vmute"],
    cmd_help={
        "help": "Remove the audio track from a video file completely.",
        "example": "vmute (replying to video)",
    },
    requires_reply=True,
)
async def video_mute(c: Client, m: Message):
    try:
        _check_ffmpeg()
    except RuntimeError as err:
        return await m.handle_message(str(err))

    msg = await m.handle_message("⏳ Downloading video to mute...")
    file_path, _ = await _download_replied_video(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid video file.")

    out_path = f"temp/xtra_videos/muted_{os.path.basename(file_path)}"

    try:
        await msg.edit_msg("🔇 Stripping audio track...")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            file_path,
            "-c:v",
            "copy",
            "-an",
            out_path,
        ]
        code, stdout, stderr = await _run_command_async(cmd)
        if code != 0 or not os.path.exists(out_path):
            return await msg.edit_msg(f"❌ Muting failed:\n<code>{stderr[-300:]}</code>")

        await msg.edit_msg("📤 Uploading muted video...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_path,
            caption="🔇 <b>Audio removed successfully.</b>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Error: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["vgif"],
    cmd_help={
        "help": "Convert replied video or short clip into a looping GIF.",
        "example": "vgif [fps] (e.g. vgif or vgif 12)",
    },
    requires_reply=True,
)
async def video_to_gif(c: Client, m: Message):
    try:
        _check_ffmpeg()
    except RuntimeError as err:
        return await m.handle_message(str(err))

    msg = await m.handle_message("⏳ Downloading video...")
    file_path, _ = await _download_replied_video(m)
    if not file_path:
        return await msg.edit_msg("❌ Please reply to a valid video file.")

    fps = 15
    if m.user_input and m.user_input.strip().isdigit():
        fps = max(5, min(30, int(m.user_input.strip())))

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    out_path = f"temp/xtra_videos/{base_name}.gif"

    try:
        await msg.edit_msg(f"🎞 Converting video to GIF ({fps} FPS)...")
        filter_str = f"fps={fps},scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd = [
            "ffmpeg",
            "-y",
            "-t",
            "15",  # Cap at 15s to prevent gigabyte GIFs
            "-i",
            file_path,
            "-vf",
            filter_str,
            out_path,
        ]
        code, stdout, stderr = await _run_command_async(cmd)
        if code != 0 or not os.path.exists(out_path):
            return await msg.edit_msg(f"❌ GIF conversion failed:\n<code>{stderr[-300:]}</code>")

        await msg.edit_msg("📤 Uploading GIF...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_path,
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Error: <code>{e}</code>")
    finally:
        for p in (file_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
