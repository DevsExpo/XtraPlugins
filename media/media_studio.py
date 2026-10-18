# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from telethon import custom
from telethon.errors import MessageNotModifiedError

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from Main.utils.custom_filters import filters

logger = logging.getLogger("friday.media_studio")

# Dependencies check
FFMPEG_PATH = shutil.which("ffmpeg")
FFPROBE_PATH = shutil.which("ffprobe")

try:
    from PIL import Image, ImageOps, ImageFilter, ImageEnhance

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_STUDIO_DIR = Path("temp/media_studio")
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_MAX_SESSION_AGE = 3600  # 1 hour TTL

# Human-readable labels for applied operations
_ACTION_LABELS = {
    # Photo Filters
    "p_bw": "🖤 Black & White",
    "p_sepia": "📜 Vintage Sepia",
    "p_contrast": "⚡ High Contrast",
    "p_blur": "🌫️ Gaussian Blur",
    "p_invert": "🔄 Invert Colors",
    "p_sharp": "🔍 Sharpen",
    "p_emboss": "🗿 Emboss",
    # Photo Lighting
    "p_bright_up": "☀️ Brightness (+25%)",
    "p_bright_dn": "🌘 Brightness (-20%)",
    "p_sat_up": "🌈 Saturation (+40%)",
    "p_sat_dn": "⚪ Saturation (-40%)",
    # Photo Orientation
    "p_r90": "↷ Rotate 90° CW",
    "p_r270": "↶ Rotate 90° CCW",
    "p_r180": "🔄 Rotate 180°",
    "p_fliph": "↔️ Mirror Horizontal",
    "p_flipv": "↕️ Flip Vertical",
    # Photo Aspect Ratios
    "p_1x1": "📐 1:1 Square Crop",
    "p_4x5": "📐 4:5 Portrait Crop",
    "p_16x9": "📐 16:9 Landscape Crop",
    "p_9x16": "📐 9:16 Story/Reel Crop",
    "p_3x4": "📐 3:4 Classic Crop",
    # Video Speed
    "v_05x": "🐢 Speed 0.5x (Slow-Mo)",
    "v_075x": "Speed 0.75x",
    "v_125x": "Speed 1.25x",
    "v_15x": "⚡ Speed 1.5x (Fast)",
    "v_20x": "🚀 Speed 2.0x (Hyperlapse)",
    # Video Orientation
    "v_r90": "↷ Rotate 90° CW",
    "v_r270": "↶ Rotate 90° CCW",
    "v_r180": "🔄 Rotate 180°",
    "v_fliph": "↔️ Mirror Horizontal",
    "v_flipv": "↕️ Flip Vertical",
    # Video Trim
    "v_t15": "✂️ Trim First 15s",
    "v_t30": "✂️ Trim First 30s",
    "v_t60": "✂️ Trim First 60s",
    "v_thalf": "✂️ Trim First 50%",
    # Video Audio
    "v_mute": "🔇 Mute Audio",
    "v_vol_up": "🔊 Volume Boost (+50%)",
    "v_vol_dn": "🔉 Volume Reduce (-50%)",
    # Video Formats & Color
    "v_togif": "🎞 Convert to GIF",
    "v_vnote": "⭕ Video Note (Circle)",
    "v_rev": "⏪ Reverse Playback",
    "v_comp": "📦 Smart Compress",
    "v_bw": "🖤 Grayscale",
    "v_sepia": "📜 Vintage Sepia",
    "v_neg": "🔄 Invert Colors",
}


def _cleanup_old_sessions():
    now = time.time()
    expired = [sid for sid, s in _SESSIONS.items() if now - s.get("created_at", 0) > _MAX_SESSION_AGE]
    for sid in expired:
        s = _SESSIONS.pop(sid, None)
        if s and "work_dir" in s:
            with contextlib.suppress(Exception):
                shutil.rmtree(s["work_dir"], ignore_errors=True)


async def _run_ffmpeg(cmd: List[str]) -> Tuple[int, str, str]:
    """Execute ffmpeg asynchronously without blocking event loop."""
    if not FFMPEG_PATH:
        raise RuntimeError("ffmpeg executable not found in system PATH.")
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


async def _get_video_info(path: str) -> Dict[str, Any]:
    """Extract video duration, resolution, codec, and streams using ffprobe."""
    if not FFPROBE_PATH:
        return {"duration": 0, "width": 0, "height": 0, "has_audio": False}
    cmd = [
        FFPROBE_PATH,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    code, stdout, _ = await _run_ffmpeg(cmd)
    if code == 0 and stdout:
        with contextlib.suppress(Exception):
            data = json.loads(stdout)
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0))
            streams = data.get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            for s in streams:
                if s.get("codec_type") == "video":
                    return {
                        "duration": duration,
                        "width": int(s.get("width", 0)),
                        "height": int(s.get("height", 0)),
                        "codec": s.get("codec_name", "mp4"),
                        "has_audio": has_audio,
                    }
    return {"duration": 0, "width": 0, "height": 0, "has_audio": False}


def _get_active_sender_client(default_client: Any) -> Any:
    """Return the active userbot client instance or fallback to the provided client."""
    if getattr(Friday, "clients", None) and len(Friday.clients) > 0:
        return Friday.clients[0]
    return default_client


def _format_time(sec: float) -> str:
    s = max(0.0, float(sec))
    m = int(s // 60)
    remaining_sec = int(s % 60)
    return f"{m:02d}:{remaining_sec:02d}"


def _parse_time_str(val: str) -> Optional[float]:
    """Parse '01:25', '85', '1:05.5' into seconds."""
    val = val.strip().lower().replace("s", "")
    if ":" in val:
        parts = val.split(":")
        if len(parts) == 2:
            try:
                return float(parts[0]) * 60 + float(parts[1])
            except ValueError:
                return None
        elif len(parts) == 3:
            try:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            except ValueError:
                return None
    try:
        return float(val)
    except ValueError:
        return None


def _default_video_recipe(total_duration: float = 0.0) -> Dict[str, Any]:
    return {
        "speed": 1.0,
        "trim_start": 0.0,
        "trim_end": round(total_duration, 1) if total_duration > 0 else 0.0,
        "trim_active": False,
        "rotate": 0,
        "flip_h": False,
        "flip_v": False,
        "mute": False,
        "volume": 1.0,
        "filter": None,
        "reverse": False,
        "format": "normal",
    }


def _toggle_video_recipe(recipe: Dict[str, Any], action: str, total_duration: float = 0.0) -> None:
    # Speed
    speed_map = {
        "v_05x": 0.5,
        "v_075x": 0.75,
        "v_125x": 1.25,
        "v_15x": 1.5,
        "v_20x": 2.0,
    }
    if action in speed_map:
        val = speed_map[action]
        recipe["speed"] = 1.0 if recipe.get("speed") == val else val
        return

    # ── Custom Stepper Cut / Trim (Never forced to presets!) ──
    dur = total_duration if total_duration > 0 else max(recipe.get("trim_end", 0.0), 300.0)
    start = recipe.get("trim_start", 0.0)
    end = recipe.get("trim_end") if (recipe.get("trim_end", 0.0) > 0) else dur

    # Start time adjustments
    if action == "v_tstart_m30":
        recipe["trim_start"] = max(0.0, start - 30.0)
        recipe["trim_active"] = bool(recipe["trim_start"] > 0 or recipe.get("trim_end", dur) < dur)
        return
    if action == "v_tstart_m5":
        recipe["trim_start"] = max(0.0, start - 5.0)
        recipe["trim_active"] = bool(recipe["trim_start"] > 0 or recipe.get("trim_end", dur) < dur)
        return
    if action == "v_tstart_p5":
        recipe["trim_start"] = min(max(0.0, end - 1.0), start + 5.0)
        recipe["trim_active"] = True
        return
    if action == "v_tstart_p30":
        recipe["trim_start"] = min(max(0.0, end - 1.0), start + 30.0)
        recipe["trim_active"] = True
        return

    # End time adjustments
    if action == "v_tend_m30":
        recipe["trim_end"] = max(start + 1.0, end - 30.0)
        recipe["trim_active"] = True
        return
    if action == "v_tend_m5":
        recipe["trim_end"] = max(start + 1.0, end - 5.0)
        recipe["trim_active"] = True
        return
    if action == "v_tend_p5":
        recipe["trim_end"] = min(dur, end + 5.0)
        recipe["trim_active"] = bool(recipe.get("trim_start", 0.0) > 0 or recipe["trim_end"] < dur)
        return
    if action == "v_tend_p30":
        recipe["trim_end"] = min(dur, end + 30.0)
        recipe["trim_active"] = bool(recipe.get("trim_start", 0.0) > 0 or recipe["trim_end"] < dur)
        return

    # Convenience Presets (Optional shortcuts)
    if action == "v_t15":
        recipe["trim_start"] = 0.0
        recipe["trim_end"] = min(15.0, dur)
        recipe["trim_active"] = True
        return
    if action == "v_t30":
        recipe["trim_start"] = 0.0
        recipe["trim_end"] = min(30.0, dur)
        recipe["trim_active"] = True
        return
    if action == "v_t60":
        recipe["trim_start"] = 0.0
        recipe["trim_end"] = min(60.0, dur)
        recipe["trim_active"] = True
        return
    if action == "v_thalf":
        recipe["trim_start"] = 0.0
        recipe["trim_end"] = max(1.0, round(dur / 2.0, 1))
        recipe["trim_active"] = True
        return
    if action == "v_treset":
        recipe["trim_start"] = 0.0
        recipe["trim_end"] = dur
        recipe["trim_active"] = False
        return

    # Rotate
    rot_map = {
        "v_r90": 90,
        "v_r270": 270,
        "v_r180": 180,
    }
    if action in rot_map:
        val = rot_map[action]
        recipe["rotate"] = 0 if recipe.get("rotate") == val else val
        return

    # Flip
    if action == "v_fliph":
        recipe["flip_h"] = not recipe.get("flip_h", False)
        return
    if action == "v_flipv":
        recipe["flip_v"] = not recipe.get("flip_v", False)
        return

    # Audio
    if action == "v_mute":
        recipe["mute"] = not recipe.get("mute", False)
        return
    if action == "v_vol_up":
        recipe["volume"] = 1.0 if recipe.get("volume") == 1.5 else 1.5
        recipe["mute"] = False
        return
    if action == "v_vol_dn":
        recipe["volume"] = 1.0 if recipe.get("volume") == 0.5 else 0.5
        recipe["mute"] = False
        return

    # Filters
    flt_map = {
        "v_bw": "bw",
        "v_sepia": "sepia",
        "v_neg": "neg",
    }
    if action in flt_map:
        val = flt_map[action]
        recipe["filter"] = None if recipe.get("filter") == val else val
        return

    # Reverse
    if action == "v_rev":
        recipe["reverse"] = not recipe.get("reverse", False)
        return

    # Format
    fmt_map = {
        "v_togif": "gif",
        "v_vnote": "vnote",
        "v_comp": "comp",
    }
    if action in fmt_map:
        val = fmt_map[action]
        recipe["format"] = "normal" if recipe.get("format") == val else val
        return


def _get_recipe_description(recipe: Dict[str, Any], duration: float = 0) -> List[str]:
    items = []
    speed = recipe.get("speed", 1.0)
    if speed != 1.0:
        label = "Slow-Mo" if speed < 1.0 else "Fast"
        items.append(f"⚡ <b>Speed:</b> {speed}x ({label})")

    if recipe.get("trim_active"):
        start = recipe.get("trim_start", 0.0)
        end = recipe.get("trim_end") if recipe.get("trim_end", 0.0) > 0 else duration
        cut_len = max(0.0, end - start)
        items.append(f"✂️ <b>Cut:</b> {_format_time(start)} ➔ {_format_time(end)} ({_format_time(cut_len)})")

    rotate = recipe.get("rotate", 0)
    if rotate:
        items.append(f"🔄 <b>Rotate:</b> {rotate}° CW")

    if recipe.get("flip_h"):
        items.append("↔️ <b>Mirror:</b> Horizontal")
    if recipe.get("flip_v"):
        items.append("↕️ <b>Flip:</b> Vertical")

    if recipe.get("mute"):
        items.append("🔇 <b>Audio:</b> Muted")
    elif recipe.get("volume", 1.0) != 1.0:
        vol = int(recipe["volume"] * 100)
        items.append(f"🔊 <b>Volume:</b> {vol}%")

    v_filter = recipe.get("filter")
    if v_filter:
        flabels = {"bw": "🖤 Grayscale", "sepia": "📜 Vintage Sepia", "neg": "🔄 Invert"}
        items.append(f"🎨 <b>Filter:</b> {flabels.get(v_filter, v_filter)}")

    if recipe.get("reverse"):
        items.append("⏪ <b>Playback:</b> Reversed")

    v_format = recipe.get("format", "normal")
    if v_format == "gif":
        items.append("🎞 <b>Export:</b> Animated GIF")
    elif v_format == "vnote":
        items.append("⭕ <b>Export:</b> Telegram Video Note (Circle)")
    elif v_format == "comp":
        items.append("📦 <b>Export:</b> High Compression MP4")

    return items


def _process_image_sync(input_path: str, output_path: str, action: str) -> str:
    """Apply non-destructive image transformation using Pillow."""
    with Image.open(input_path) as img:
        if action in ("p_jpg",) and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # ── Filters ──
        if action in ("p_bw", "v_bw"):
            img = ImageOps.grayscale(img)
        elif action in ("p_sepia", "v_sepia"):
            gray = ImageOps.grayscale(img)
            img = ImageOps.colorize(gray, "#704214", "#ffecb3")
        elif action in ("p_contrast",):
            enh = ImageEnhance.Contrast(img)
            img = enh.enhance(1.6)
        elif action == "p_blur":
            img = img.filter(ImageFilter.GaussianBlur(radius=6))
        elif action in ("p_invert", "v_neg"):
            if img.mode != "RGB":
                img = img.convert("RGB")
            img = ImageOps.invert(img)
        elif action == "p_sharp":
            enh = ImageEnhance.Sharpness(img)
            img = enh.enhance(2.0)
        elif action == "p_emboss":
            img = img.filter(ImageFilter.EMBOSS)

        # ── Lighting ──
        elif action == "p_bright_up":
            enh = ImageEnhance.Brightness(img)
            img = enh.enhance(1.25)
        elif action == "p_bright_dn":
            enh = ImageEnhance.Brightness(img)
            img = enh.enhance(0.8)
        elif action == "p_sat_up":
            enh = ImageEnhance.Color(img)
            img = enh.enhance(1.4)
        elif action == "p_sat_dn":
            enh = ImageEnhance.Color(img)
            img = enh.enhance(0.6)

        # ── Orientation ──
        elif action in ("p_r90", "v_r90"):
            img = img.rotate(-90, expand=True)
        elif action in ("p_r270", "v_r270"):
            img = img.rotate(90, expand=True)
        elif action in ("p_r180", "v_r180"):
            img = img.rotate(180, expand=True)
        elif action in ("p_fliph", "v_fliph"):
            img = ImageOps.mirror(img)
        elif action in ("p_flipv", "v_flipv"):
            img = ImageOps.flip(img)

        # ── Aspect Ratios & Crop ──
        elif action in ("p_1x1", "p_4x5", "p_16x9", "p_9x16", "p_3x4"):
            ratios = {
                "p_1x1": (1, 1),
                "p_4x5": (4, 5),
                "p_16x9": (16, 9),
                "p_9x16": (9, 16),
                "p_3x4": (3, 4),
            }
            rw, rh = ratios[action]
            w, h = img.size
            target_ratio = rw / rh
            current_ratio = w / h

            if current_ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            else:
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))

        # Save output
        if action == "p_webp":
            img.save(output_path, format="WEBP")
        elif action == "p_jpg":
            img.save(output_path, format="JPEG", quality=95)
        else:
            img.save(output_path, format="PNG")
    return output_path


def _generate_lightweight_thumbnail(input_path: str, thumb_path: str, max_size: int = 480) -> str:
    """Generate a lightweight, highly-compressed low-res proxy (~15KB) for instant live view."""
    with Image.open(input_path) as img:
        img_copy = img.copy()
        if img_copy.mode in ("RGBA", "P"):
            img_copy = img_copy.convert("RGB")
        img_copy.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        img_copy.save(thumb_path, format="JPEG", quality=65, optimize=True)
    return thumb_path


async def _compile_video_export(
    input_path: str,
    output_path: str,
    recipe: Dict[str, Any],
    duration: float,
    has_audio: bool = True,
) -> str:
    """
    Single-pass compound ffmpeg compilation:
    Preserves original video quality and applies all speed, trim, transform, audio,
    and color filters in one single pass. Output is guaranteed universally streamable
    H.264 (yuv420p) with faststart flags.
    """
    vf_filters: List[str] = []
    af_filters: List[str] = []

    speed = recipe.get("speed", 1.0)
    rotate = recipe.get("rotate", 0)
    flip_h = recipe.get("flip_h", False)
    flip_v = recipe.get("flip_v", False)
    mute = recipe.get("mute", False)
    volume = recipe.get("volume", 1.0)
    v_filter = recipe.get("filter")
    reverse = recipe.get("reverse", False)
    v_format = recipe.get("format", "normal")

    # 1. Speed
    if speed != 1.0:
        pts = round(1.0 / speed, 4)
        vf_filters.append(f"setpts={pts}*PTS")
        if speed == 0.5:
            af_filters.append("atempo=0.5")
        elif speed == 0.75:
            af_filters.append("atempo=0.75")
        elif speed == 1.25:
            af_filters.append("atempo=1.25")
        elif speed == 1.5:
            af_filters.append("atempo=1.5")
        elif speed == 2.0:
            af_filters.append("atempo=2.0")
        else:
            af_filters.append(f"atempo={speed}")

    # 2. Orientation & Transform
    if rotate == 90:
        vf_filters.append("transpose=1")
    elif rotate == 270:
        vf_filters.append("transpose=2")
    elif rotate == 180:
        vf_filters.append("hflip,vflip")
    if flip_h:
        vf_filters.append("hflip")
    if flip_v:
        vf_filters.append("vflip")

    # 3. Filters
    if v_filter == "bw":
        vf_filters.append("hue=s=0")
    elif v_filter == "sepia":
        vf_filters.append("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
    elif v_filter == "neg":
        vf_filters.append("negate")

    # 4. Reverse
    if reverse:
        vf_filters.append("reverse")
        af_filters.append("areverse")

    # 5. Video Note crop (Circle 1:1)
    if v_format == "vnote":
        vf_filters.append("crop=min(iw\\,ih):min(iw\\,ih),scale=384:384")

    # 6. Volume
    if volume != 1.0 and volume > 0:
        af_filters.append(f"volume={volume}")

    # ── Custom Frame-Accurate Cut / Trim ──
    trim_active = recipe.get("trim_active", False)
    start_sec = max(0.0, float(recipe.get("trim_start", 0.0))) if trim_active else 0.0
    end_sec = float(recipe.get("trim_end", 0.0)) if (trim_active and recipe.get("trim_end", 0.0) > 0) else None

    # Build command
    cmd = [FFMPEG_PATH, "-y"]

    if trim_active:
        if start_sec > 0:
            cmd.extend(["-ss", str(round(start_sec, 2))])
        if end_sec is not None and end_sec > start_sec:
            cut_dur = end_sec - start_sec
            cmd.extend(["-t", str(round(cut_dur, 2))])

    cmd.extend(["-i", input_path])

    if v_format == "gif":
        vf_chain = ",".join(vf_filters) if vf_filters else ""
        if vf_chain:
            vf_chain += ","
        vf_chain += "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd.extend(["-vf", vf_chain, "-loop", "0", output_path])
    else:
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        # Audio handling
        if mute or not has_audio:
            cmd.append("-an")
        elif af_filters:
            cmd.extend(["-af", ",".join(af_filters)])
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.extend(["-c:a", "copy"])

        # High-performance universal H.264
        preset = "ultrafast" if v_format == "comp" else "fast"
        crf = "28" if v_format == "comp" else "22"
        cmd.extend(
            ["-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        )

        cmd.append(output_path)

    code, _, err = await _run_ffmpeg(cmd)
    if code != 0:
        raise RuntimeError(f"Video compilation failed: {err[:200]}")
    return output_path


async def _generate_video_frame_preview(video_path: str, thumb_path: str) -> str:
    """Extract a fast preview frame from video (~15KB JPEG) for live inspection."""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss",
        "00:00:01",
        "-i",
        video_path,
        "-vframes",
        "1",
        "-vf",
        "scale=480:-1",
        "-q:v",
        "4",
        thumb_path,
    ]
    code, _, _ = await _run_ffmpeg(cmd)
    if code != 0 or not os.path.exists(thumb_path):
        cmd[2] = "00:00:00"
        await _run_ffmpeg(cmd)
    return thumb_path


def _build_studio_text(session: Dict[str, Any], menu: str = "main") -> str:
    m_type = session["type"]
    name = "🎬 Video Studio" if m_type == "video" else "📸 Photo Studio"
    info = session.get("info", {})

    meta_parts = []
    if m_type == "video":
        dur = info.get("duration", 0)
        dur_str = f"{int(dur // 60)}m {int(dur % 60)}s" if dur else "N/A"
        meta_parts.append(f"⏱ <b>Duration:</b> {dur_str}")
        if info.get("width"):
            meta_parts.append(f"📐 <b>Res:</b> {info['width']}×{info['height']}")
        if info.get("codec"):
            meta_parts.append(f"🎞 <b>Codec:</b> {info['codec'].upper()}")
    else:
        if info.get("width"):
            meta_parts.append(f"📐 <b>Resolution:</b> {info['width']}×{info['height']}")

    meta_line = " · ".join(meta_parts) if meta_parts else ""

    if m_type == "video":
        recipe = session.get("video_recipe") or _default_video_recipe()
        recipe_lines = _get_recipe_description(recipe, info.get("duration", 0))
        if recipe_lines:
            recipe_block = (
                f"\n📋 <b>Staged Recipe ({len(recipe_lines)} ready to apply):</b>\n"
                + "\n".join(f"  • {item}" for item in recipe_lines)
                + "\n"
            )
        else:
            recipe_block = "\n<i>No edits staged yet (Original file untouched).</i>\n"
    else:
        applied_actions = session.get("action_history", [])
        if applied_actions:
            history_lines = []
            for idx, act in enumerate(applied_actions[-4:], start=max(1, len(applied_actions) - 3)):
                lbl = _ACTION_LABELS.get(act, act)
                history_lines.append(f"  {idx}. <code>{lbl}</code>")
            if len(applied_actions) > 4:
                history_lines.insert(0, f"  <i>… +{len(applied_actions) - 4} earlier changes</i>")
            recipe_block = "\n<b>Pipeline Recipe:</b>\n" + "\n".join(history_lines) + "\n"
        else:
            recipe_block = "\n<i>No edits applied yet (Original file).</i>\n"

    menu_titles = {
        "main": "🎛️ <b>Editing Console</b>",
        "p_flt": "🎨 <b>Color Filters</b>",
        "p_asp": "📐 <b>Crop & Aspect Ratio</b>",
        "p_rot": "🔄 <b>Rotate & Mirror</b>",
        "p_lit": "☀️ <b>Lighting & Color Lab</b>",
        "p_exp": "🖼 <b>Export Format Selection</b>",
        "v_trm": "✂️ <b>Trim & Cut Presets</b>",
        "v_spd": "⚡ <b>Speed & Motion Lab</b>",
        "v_rot": "🔄 <b>Orientation & Transform</b>",
        "v_aud": "🔊 <b>Audio Controls & MP3</b>",
        "v_col": "🎨 <b>Color Grading</b>",
    }
    title = menu_titles.get(menu, "🎛️ <b>Editing Console</b>")

    if m_type == "video":
        instruction = "<i>Stage your desired edits below, then tap 'Apply & Render':</i>"
    else:
        instruction = "<i>Tap any tool below to update the preview live:</i>"

    return f"{name}\n• {meta_line}\n{recipe_block}\n{title}\n{instruction}"


def _build_studio_keyboard(session: Dict[str, Any], menu: str = "main") -> List[List[Any]]:
    sid = session["id"]
    m_type = session["type"]
    info = session.get("info", {})
    has_undo = bool(session.get("action_history"))

    # ── PHOTO MENUS ──
    if m_type == "photo":
        if menu == "p_flt":
            return [
                [
                    custom.Button.inline("🖤 B&W", f"ms_{sid}_act_p_bw".encode()),
                    custom.Button.inline("📜 Sepia", f"ms_{sid}_act_p_sepia".encode()),
                    custom.Button.inline("⚡ Contrast", f"ms_{sid}_act_p_contrast".encode()),
                ],
                [
                    custom.Button.inline("🌫️ Blur", f"ms_{sid}_act_p_blur".encode()),
                    custom.Button.inline("🔄 Invert", f"ms_{sid}_act_p_invert".encode()),
                    custom.Button.inline("🔍 Sharpen", f"ms_{sid}_act_p_sharp".encode()),
                ],
                [
                    custom.Button.inline("🗿 Emboss", f"ms_{sid}_act_p_emboss".encode()),
                    custom.Button.inline("⬅️ Back", f"ms_{sid}_nav_main".encode()),
                ],
            ]

        if menu == "p_asp":
            return [
                [
                    custom.Button.inline("1:1 Square", f"ms_{sid}_act_p_1x1".encode()),
                    custom.Button.inline("4:5 Portrait", f"ms_{sid}_act_p_4x5".encode()),
                ],
                [
                    custom.Button.inline("16:9 Landscape", f"ms_{sid}_act_p_16x9".encode()),
                    custom.Button.inline("9:16 Story/Reel", f"ms_{sid}_act_p_9x16".encode()),
                ],
                [
                    custom.Button.inline("3:4 Classic", f"ms_{sid}_act_p_3x4".encode()),
                    custom.Button.inline("⬅️ Back", f"ms_{sid}_nav_main".encode()),
                ],
            ]

        if menu == "p_rot":
            return [
                [
                    custom.Button.inline("↷ 90° CW", f"ms_{sid}_act_p_r90".encode()),
                    custom.Button.inline("↶ 90° CCW", f"ms_{sid}_act_p_r270".encode()),
                    custom.Button.inline("🔄 180°", f"ms_{sid}_act_p_r180".encode()),
                ],
                [
                    custom.Button.inline("↔️ Mirror H", f"ms_{sid}_act_p_fliph".encode()),
                    custom.Button.inline("↕️ Flip V", f"ms_{sid}_act_p_flipv".encode()),
                    custom.Button.inline("⬅️ Back", f"ms_{sid}_nav_main".encode()),
                ],
            ]

        if menu == "p_lit":
            return [
                [
                    custom.Button.inline("☀️ Bright +", f"ms_{sid}_act_p_bright_up".encode()),
                    custom.Button.inline("🌘 Bright -", f"ms_{sid}_act_p_bright_dn".encode()),
                ],
                [
                    custom.Button.inline("🌈 Saturation +", f"ms_{sid}_act_p_sat_up".encode()),
                    custom.Button.inline("⚪ Saturation -", f"ms_{sid}_act_p_sat_dn".encode()),
                ],
                [
                    custom.Button.inline("⬅️ Back", f"ms_{sid}_nav_main".encode()),
                ],
            ]

        if menu == "p_exp":
            return [
                [
                    custom.Button.inline("🖼 PNG (Lossless)", f"ms_{sid}_save_png".encode()),
                    custom.Button.inline("📷 High-Q JPG", f"ms_{sid}_save_jpg".encode()),
                ],
                [
                    custom.Button.inline("🎭 WebP Sticker", f"ms_{sid}_save_webp".encode()),
                    custom.Button.inline("⬅️ Back", f"ms_{sid}_nav_main".encode()),
                ],
            ]

        # Main Photo Menu
        rows = [
            [
                custom.Button.inline("🎨 Filters", f"ms_{sid}_nav_p_flt".encode()),
                custom.Button.inline("📐 Aspect Crop", f"ms_{sid}_nav_p_asp".encode()),
            ],
            [
                custom.Button.inline("🔄 Rotate / Flip", f"ms_{sid}_nav_p_rot".encode()),
                custom.Button.inline("☀️ Lighting Lab", f"ms_{sid}_nav_p_lit".encode()),
            ],
            [
                custom.Button.inline("🖼 Export As…", f"ms_{sid}_nav_p_exp".encode()),
            ],
        ]
        action_row = []
        if has_undo:
            action_row.append(custom.Button.inline("↩️ Undo", f"ms_{sid}_undo".encode()))
        action_row.append(custom.Button.inline("💾 Send Photo", f"ms_{sid}_done".encode()))
        action_row.append(custom.Button.inline("❌ Close", f"ms_{sid}_close".encode()))
        rows.append(action_row)
        return rows

    # ── VIDEO MENUS ──
    recipe = session.get("video_recipe") or _default_video_recipe()

    if menu == "v_trm":
        dur = info.get("duration", 0.0)
        start = recipe.get("trim_start", 0.0)
        end = recipe.get("trim_end") if (recipe.get("trim_end", 0.0) > 0) else dur
        cut_len = max(0.0, end - start)

        return [
            # Row 1: Start Time Stepper
            [
                custom.Button.inline(f"Start: {_format_time(start)}", f"ms_{sid}_noop".encode()),
                custom.Button.inline("-30s", f"ms_{sid}_act_v_tstart_m30".encode()),
                custom.Button.inline("-5s", f"ms_{sid}_act_v_tstart_m5".encode()),
                custom.Button.inline("+5s", f"ms_{sid}_act_v_tstart_p5".encode()),
                custom.Button.inline("+30s", f"ms_{sid}_act_v_tstart_p30".encode()),
            ],
            # Row 2: End Time Stepper
            [
                custom.Button.inline(f"End: {_format_time(end)}", f"ms_{sid}_noop".encode()),
                custom.Button.inline("-30s", f"ms_{sid}_act_v_tend_m30".encode()),
                custom.Button.inline("-5s", f"ms_{sid}_act_v_tend_m5".encode()),
                custom.Button.inline("+5s", f"ms_{sid}_act_v_tend_p5".encode()),
                custom.Button.inline("+30s", f"ms_{sid}_act_v_tend_p30".encode()),
            ],
            # Row 3: Presets (Quick convenience, never forced!)
            [
                custom.Button.inline("⏱ 15s", f"ms_{sid}_act_v_t15".encode()),
                custom.Button.inline("⏱ 30s", f"ms_{sid}_act_v_t30".encode()),
                custom.Button.inline("⏱ 60s", f"ms_{sid}_act_v_t60".encode()),
                custom.Button.inline("✂️ 50%", f"ms_{sid}_act_v_thalf".encode()),
            ],
            # Row 4: Cut Length & Reset
            [
                custom.Button.inline(f"✂️ Length: {_format_time(cut_len)}", f"ms_{sid}_noop".encode()),
                custom.Button.inline("🔄 Reset Cut", f"ms_{sid}_act_v_treset".encode()),
            ],
            [
                custom.Button.inline("✍️ Type Custom (.vtrim)", f"ms_{sid}_act_v_tprompt".encode()),
                custom.Button.inline("⬅️ Back to Console", f"ms_{sid}_nav_main".encode()),
            ],
        ]

    if menu == "v_spd":
        cur_spd = recipe.get("speed", 1.0)
        return [
            [
                custom.Button.inline(f"🐢 0.5x Slow {'✅' if cur_spd == 0.5 else ''}", f"ms_{sid}_act_v_05x".encode()),
                custom.Button.inline(f"0.75x {'✅' if cur_spd == 0.75 else ''}", f"ms_{sid}_act_v_075x".encode()),
            ],
            [
                custom.Button.inline(f"1.25x {'✅' if cur_spd == 1.25 else ''}", f"ms_{sid}_act_v_125x".encode()),
                custom.Button.inline(f"⚡ 1.5x Fast {'✅' if cur_spd == 1.5 else ''}", f"ms_{sid}_act_v_15x".encode()),
                custom.Button.inline(f"🚀 2.0x {'✅' if cur_spd == 2.0 else ''}", f"ms_{sid}_act_v_20x".encode()),
            ],
            [
                custom.Button.inline("⬅️ Back to Console", f"ms_{sid}_nav_main".encode()),
            ],
        ]

    if menu == "v_rot":
        cur_rot = recipe.get("rotate", 0)
        return [
            [
                custom.Button.inline(f"↷ 90° CW {'✅' if cur_rot == 90 else ''}", f"ms_{sid}_act_v_r90".encode()),
                custom.Button.inline(f"↶ 90° CCW {'✅' if cur_rot == 270 else ''}", f"ms_{sid}_act_v_r270".encode()),
            ],
            [
                custom.Button.inline(f"🔄 180° {'✅' if cur_rot == 180 else ''}", f"ms_{sid}_act_v_r180".encode()),
                custom.Button.inline(
                    f"↔️ Mirror H {'✅' if recipe.get('flip_h') else ''}", f"ms_{sid}_act_v_fliph".encode()
                ),
                custom.Button.inline(
                    f"↕️ Flip V {'✅' if recipe.get('flip_v') else ''}", f"ms_{sid}_act_v_flipv".encode()
                ),
            ],
            [
                custom.Button.inline("⬅️ Back to Console", f"ms_{sid}_nav_main".encode()),
            ],
        ]

    if menu == "v_aud":
        cur_mute = recipe.get("mute", False)
        cur_vol = recipe.get("volume", 1.0)
        return [
            [
                custom.Button.inline(f"🔇 Mute Audio {'✅' if cur_mute else ''}", f"ms_{sid}_act_v_mute".encode()),
                custom.Button.inline("🎵 Extract MP3", f"ms_{sid}_act_v_extract_mp3".encode()),
            ],
            [
                custom.Button.inline(
                    f"🔊 Vol +50% {'✅' if cur_vol == 1.5 else ''}", f"ms_{sid}_act_v_vol_up".encode()
                ),
                custom.Button.inline(
                    f"🔉 Vol -50% {'✅' if cur_vol == 0.5 else ''}", f"ms_{sid}_act_v_vol_dn".encode()
                ),
            ],
            [
                custom.Button.inline("⬅️ Back to Console", f"ms_{sid}_nav_main".encode()),
            ],
        ]

    if menu == "v_col":
        cur_flt = recipe.get("filter")
        return [
            [
                custom.Button.inline(f"🖤 Grayscale {'✅' if cur_flt == 'bw' else ''}", f"ms_{sid}_act_v_bw".encode()),
                custom.Button.inline(
                    f"📜 Vintage Sepia {'✅' if cur_flt == 'sepia' else ''}", f"ms_{sid}_act_v_sepia".encode()
                ),
            ],
            [
                custom.Button.inline(
                    f"🔄 Invert Colors {'✅' if cur_flt == 'neg' else ''}", f"ms_{sid}_act_v_neg".encode()
                ),
                custom.Button.inline("⬅️ Back to Console", f"ms_{sid}_nav_main".encode()),
            ],
        ]

    # Main Video Menu
    cur_fmt = recipe.get("format", "normal")
    is_rev = recipe.get("reverse", False)
    staged_count = len(_get_recipe_description(recipe, session.get("info", {}).get("duration", 0)))

    rows = [
        [
            custom.Button.inline("✂️ Trim / Cut", f"ms_{sid}_nav_v_trm".encode()),
            custom.Button.inline("⚡ Speed Lab", f"ms_{sid}_nav_v_spd".encode()),
        ],
        [
            custom.Button.inline("🔄 Transform", f"ms_{sid}_nav_v_rot".encode()),
            custom.Button.inline("🔊 Audio / MP3", f"ms_{sid}_nav_v_aud".encode()),
        ],
        [
            custom.Button.inline(
                f"🎞 Convert to GIF {'✅' if cur_fmt == 'gif' else ''}", f"ms_{sid}_act_v_togif".encode()
            ),
            custom.Button.inline(
                f"⭕ Video Note {'✅' if cur_fmt == 'vnote' else ''}", f"ms_{sid}_act_v_vnote".encode()
            ),
        ],
        [
            custom.Button.inline(f"⏪ Reverse {'✅' if is_rev else ''}", f"ms_{sid}_act_v_rev".encode()),
            custom.Button.inline(f"📦 Compress {'✅' if cur_fmt == 'comp' else ''}", f"ms_{sid}_act_v_comp".encode()),
        ],
        [
            custom.Button.inline("🎨 Color Grading", f"ms_{sid}_nav_v_col".encode()),
        ],
    ]

    action_row = []
    render_label = f"🚀 Apply & Render ({staged_count})" if staged_count > 0 else "🚀 Render Video"
    action_row.append(custom.Button.inline(render_label, f"ms_{sid}_done".encode()))
    if staged_count > 0:
        action_row.append(custom.Button.inline("🗑️ Reset", f"ms_{sid}_reset".encode()))
    action_row.append(custom.Button.inline("❌ Close", f"ms_{sid}_close".encode()))
    rows.append(action_row)
    return rows


@Friday.register_on_cmd(
    ["edit", "editor", "studio", "vedit", "iedit"],
    cmd_help={
        "help": (
            "Open the Interactive Pro Media Studio with real-time live preview and inline editing buttons.\n"
            "Features: Crop, Filters, Speed, Trim, Audio/Mute, Reverse, GIF, Video Notes, and more!"
        ),
        "example": [
            "edit (replying to photo or video)",
            "vedit (replying to video)",
            "iedit (replying to photo)",
        ],
    },
    requires_reply=True,
)
@log_errors
async def media_studio_cmd(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ <i>Please reply to a photo, sticker, or video to open Media Studio.</i>")

    mime = getattr(rm.file, "mime_type", "") or ""
    is_video = bool(rm.video or rm.video_note or mime.startswith("video/"))
    is_photo = bool(rm.photo or rm.sticker or mime.startswith("image/"))

    if not is_video and not is_photo:
        return await m.handle_message("❌ <i>Replied message is not an image or video.</i>")

    status = await m.handle_message("🎛️ <i>Initializing Media Studio…</i>")

    _cleanup_old_sessions()
    session_id = uuid.uuid4().hex[:8]
    work_dir = _STUDIO_DIR / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Download replied file
    orig_path = await rm.download_media(str(work_dir / "original"))
    if not orig_path or not os.path.exists(orig_path):
        if status:
            await status.delete_if_self()
        return await m.handle_message("❌ <i>Failed to download media for editing.</i>")

    # Gather metadata and build initial low-res live preview proxy (~15KB)
    media_info: Dict[str, Any] = {}
    init_proxy_path = str(work_dir / "proxy_step_0.jpg")

    if is_video:
        media_info = await _get_video_info(orig_path)
        await _generate_video_frame_preview(orig_path, init_proxy_path)
    elif HAS_PIL:
        with contextlib.suppress(Exception):
            with Image.open(orig_path) as pimg:
                media_info = {"width": pimg.width, "height": pimg.height}
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _generate_lightweight_thumbnail, orig_path, init_proxy_path, 480)

    session = {
        "id": session_id,
        "type": "video" if is_video else "photo",
        "chat_id": m.chat_id,
        "user_id": m.sender_id,
        "reply_to_msg_id": rm.id,
        "work_dir": str(work_dir),
        "original_file": orig_path,
        "current_file": orig_path,
        "current_proxy": init_proxy_path,
        "history": [],
        "proxy_history": [],
        "action_history": [],
        "video_recipe": _default_video_recipe(),
        "info": media_info,
        "step_counter": 0,
        "created_at": time.time(),
    }
    _SESSIONS[session_id] = session

    text = _build_studio_text(session, "main")
    buttons = _build_studio_keyboard(session, "main")

    # 1. Try inline query via assistant bot
    sent = False
    if getattr(Friday, "bot_info", None) and getattr(Friday.bot_info, "username", None):
        try:
            results = await c.get_inline_bot_results(Friday.bot_info.username, f"studio {session_id}")
            if results:
                await results[0].click(m.chat_id)
                sent = True
                if status:
                    await status.delete_if_self()
        except Exception as exc:
            logger.debug(f"Media studio inline query error: {exc}")

    # 2. Fallback: direct send with preview photo if bot is in the chat
    if not sent and getattr(Friday, "_raw_bot", None):
        try:
            await Friday._raw_bot.send_file(
                m.chat_id,
                file=init_proxy_path,
                caption=text,
                buttons=buttons,
                parse_mode="html",
            )
            sent = True
            if status:
                await status.delete_if_self()
        except Exception as exc:
            logger.debug(f"Media studio direct send error: {exc}")

    # 3. Fallback: Group forbids inline bots or bot not in group -> Provide instant command shortcuts
    if not sent:
        if status:
            await status.delete_if_self()
        fallback_text = (
            "🎛️ <b>Media Studio: Quick Controls</b>\n"
            "<i>Interactive buttons are disabled in this chat by group permissions.</i>\n\n"
            "<b>Instant Command Shortcuts (replying to this media):</b>\n"
            "• <b>Resize:</b> <code>.iresize 512x512</code>\n"
            "• <b>Blur:</b> <code>.iblur 15</code>\n"
            "• <b>Rotate / Flip:</b> <code>.irotate 90</code> · <code>.iflip</code>\n"
            "• <b>Speed:</b> <code>.vspeed 1.5</code> · <code>.vspeed 0.5</code>\n"
            "• <b>Trim:</b> <code>.vtrim 0 30</code>\n"
            "• <b>Format:</b> <code>.vtogif</code> · <code>.vcircle</code>\n"
            "• <b>Audio:</b> <code>.vmute</code> · <code>.vtoaudio</code>\n\n"
            "💡 <i>Tip: Forward media to Saved Messages or a private chat with the bot to use full live interactive buttons!</i>"
        )
        await m.handle_message(fallback_text)


if getattr(Friday, "bot", None):

    @Friday.bot.on_inline_query(filters.regex(r"^studio\s+([a-zA-Z0-9]+)"))
    @log_errors
    async def studio_inline_query_handler(c, iq):
        match = re.search(r"^studio\s+([a-zA-Z0-9]+)", iq.text or "")
        if not match:
            return
        session_id = match.group(1)
        session = _SESSIONS.get(session_id)
        if not session:
            return

        text = _build_studio_text(session, "main")
        buttons = _build_studio_keyboard(session, "main")
        builder = iq.builder
        proxy_path = session.get("current_proxy")

        # Deliver photo message with inline buttons attached
        if proxy_path and os.path.exists(proxy_path):
            result = builder.photo(
                file=proxy_path,
                text=text,
                parse_mode="html",
                buttons=buttons,
            )
        else:
            name = "Video Studio" if session["type"] == "video" else "Photo Studio"
            result = builder.article(
                title=f"🎛️ Media Studio: {name}",
                description="Interactive Photo & Video Editor Console",
                text=text,
                parse_mode="html",
                buttons=buttons,
            )
        await iq.answer([result], cache_time=0)

    @Friday.bot.on_callback_query(pattern=r"^ms_")
    async def studio_callback(c, cq):
        data = cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data)
        parts = data.split("_", 3)
        if len(parts) < 3:
            return await cq.answer("Invalid studio request.")

        session_id = parts[1]
        action_type = parts[2]
        action_param = parts[3] if len(parts) > 3 else ""

        session = _SESSIONS.get(session_id)
        if not session:
            return await cq.answer("⚠️ Session expired. Please run .edit again.", alert=True)

        if cq.sender_id != session["user_id"]:
            return await cq.answer("⛔ Only the user who opened this studio can edit this media!", alert=True)

        # ── Ignored / Info Click ──
        if action_type == "noop" or action_param == "noop":
            return await cq.answer()

        # ── Navigation Submenus ──
        if action_type == "nav":
            text = _build_studio_text(session, action_param)
            buttons = _build_studio_keyboard(session, action_param)
            with contextlib.suppress(MessageNotModifiedError, Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer()

        # ── Reset Staged Video Edits ──
        if action_type == "reset":
            dur = session.get("info", {}).get("duration", 0.0)
            session["video_recipe"] = _default_video_recipe(dur)
            session.get("action_history", []).clear()
            text = _build_studio_text(session, "main")
            buttons = _build_studio_keyboard(session, "main")
            with contextlib.suppress(MessageNotModifiedError, Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer("🗑️ Cleared all staged edits.")

        # ── Undo Action ──
        if action_type == "undo":
            if not session.get("action_history"):
                return await cq.answer("Nothing to undo!", alert=True)

            if session.get("history"):
                prev_file = session["history"].pop()
                session["current_file"] = prev_file

            if session.get("proxy_history"):
                prev_proxy = session["proxy_history"].pop()
                session["current_proxy"] = prev_proxy

            session["action_history"].pop()

            text = _build_studio_text(session, "main")
            buttons = _build_studio_keyboard(session, "main")

            try:
                await cq.edit(text, file=session["current_proxy"], buttons=buttons, parse_mode="html")
            except Exception:
                with contextlib.suppress(MessageNotModifiedError, Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer("↩️ Undone last edit.")

        # ── Close Studio ──
        if action_type == "close":
            work_dir = session.get("work_dir")
            _SESSIONS.pop(session_id, None)
            if work_dir and os.path.exists(work_dir):
                with contextlib.suppress(Exception):
                    shutil.rmtree(work_dir, ignore_errors=True)
            with contextlib.suppress(MessageNotModifiedError, Exception):
                await cq.edit("🎛️ <i>Media Studio closed.</i>", buttons=None, parse_mode="html")
            return await cq.answer("Studio closed.")

        # ── Save / Done & Apply: Render and Send Final Media ──
        if action_type in ("done", "save", "apply"):
            orig_file = session["original_file"]
            dur = session.get("info", {}).get("duration", 0.0)
            recipe = session.get("video_recipe") or _default_video_recipe(dur)
            info = session.get("info", {})
            has_audio = info.get("has_audio", True)
            staged_lines = _get_recipe_description(recipe, dur)

            if not os.path.exists(orig_file):
                return await cq.answer("❌ Original file not found.", alert=True)

            await cq.answer("🚀 Compiling and rendering media…")

            # Update status message to indicate rendering
            with contextlib.suppress(MessageNotModifiedError, Exception):
                render_msg = (
                    "⏳ <b>Rendering Video…</b>\n"
                    f"• Applying {len(staged_lines)} staged edit(s)…\n"
                    "• Encoding with universal H.264 (yuv420p) · Faststart\n\n"
                    "<i>Please wait while ffmpeg processes your video…</i>"
                )
                await cq.edit(render_msg, buttons=None, parse_mode="html")

            try:
                export_target = session["current_file"]
                v_format = recipe.get("format", "normal")
                ext = ".gif" if v_format == "gif" else ".mp4"

                # Video Single-Pass Compile on Original File
                if session["type"] == "video":
                    compiled_path = str(Path(session["work_dir"]) / f"final_export{ext}")
                    await _compile_video_export(orig_file, compiled_path, recipe, dur, has_audio)
                    export_target = compiled_path

                # Photo Export
                elif session["type"] == "photo":
                    if action_type == "save" and action_param in ("png", "jpg", "webp"):
                        ext = "webp" if action_param == "webp" else "jpg" if action_param == "jpg" else "png"
                        converted_path = str(Path(session["work_dir"]) / f"export.{ext}")
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None, _process_image_sync, session["current_file"], converted_path, f"p_{action_param}"
                        )
                        export_target = converted_path

                steps_count = (
                    len(staged_lines) if session["type"] == "video" else len(session.get("action_history", []))
                )
                applied_summary = (
                    "\n• <b>Edits Applied:</b>\n" + "\n".join(f"  • {item}" for item in staged_lines)
                    if staged_lines
                    else ""
                )

                caption = (
                    f"✨ <b>Edited with Media Studio</b>\n"
                    f"• <b>Total Edits:</b> {steps_count}\n"
                    f"• <b>Type:</b> {session['type'].title()}"
                    f"{applied_summary}"
                )

                is_vnote = bool(v_format == "vnote")
                is_gif = bool(v_format == "gif" or ext == ".gif")

                # Robust client dispatch (userbot client first, fallback to bot client)
                sender_client = _get_active_sender_client(c)
                try:
                    await sender_client.send_file(
                        session["chat_id"],
                        file=export_target,
                        caption=caption,
                        parse_mode="html",
                        reply_to=session.get("reply_to_msg_id"),
                        supports_streaming=(ext == ".mp4" and not is_vnote),
                        video_note=is_vnote,
                        animation=is_gif,
                    )
                except Exception as exc:
                    logger.warning(f"Primary client send failed, falling back to bot: {exc}")
                    try:
                        await c.send_file(
                            session["chat_id"],
                            file=export_target,
                            caption=caption,
                            parse_mode="html",
                            reply_to=session.get("reply_to_msg_id"),
                            supports_streaming=(ext == ".mp4" and not is_vnote),
                            video_note=is_vnote,
                            animation=is_gif,
                        )
                    except Exception as exc2:
                        logger.error(f"Failed to send final media: {exc2}")
                        return await cq.answer(f"Upload error: {exc2}", alert=True)

                # Cleanup session directory
                work_dir = session.get("work_dir")
                _SESSIONS.pop(session_id, None)
                if work_dir and os.path.exists(work_dir):
                    with contextlib.suppress(Exception):
                        shutil.rmtree(work_dir, ignore_errors=True)

                with contextlib.suppress(MessageNotModifiedError, Exception):
                    await cq.edit(
                        f"✅ <b>Video Rendered & Sent!</b>\n"
                        f"• <b>Edits Applied:</b> {steps_count}\n"
                        f"• <b>Format:</b> {ext.upper().replace('.', '')}",
                        buttons=None,
                        parse_mode="html",
                    )
                return

            except Exception as render_exc:
                logger.error(f"Render export error: {render_exc}")
                with contextlib.suppress(MessageNotModifiedError, Exception):
                    await cq.edit(
                        f"❌ <b>Render failed:</b> <code>{str(render_exc)[:120]}</code>",
                        buttons=None,
                        parse_mode="html",
                    )
                return await cq.answer(f"Render error: {str(render_exc)[:80]}", alert=True)

        # ── Execute Processing Action (act) ──
        if action_type == "act":
            action = action_param
            action_label = _ACTION_LABELS.get(action, "effect")

            # ── VIDEO: Non-Destructive Staging in Recipe (Ultra-Fast Response) ──
            if session["type"] == "video":
                # Audio extraction completes immediately on original file
                if action == "v_extract_mp3":
                    await cq.answer("🎵 Extracting audio…")
                    sender_client = _get_active_sender_client(c)
                    mp3_path = str(Path(session["work_dir"]) / "extracted_audio.mp3")
                    cmd = [
                        FFMPEG_PATH,
                        "-y",
                        "-i",
                        session["original_file"],
                        "-vn",
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        "192k",
                        mp3_path,
                    ]
                    code, _, err = await _run_ffmpeg(cmd)
                    if code == 0 and os.path.exists(mp3_path):
                        await sender_client.send_file(
                            session["chat_id"],
                            file=mp3_path,
                            caption="🎵 <b>Audio extracted from video</b>",
                            parse_mode="html",
                            reply_to=session.get("reply_to_msg_id"),
                        )
                        return await cq.answer("🎵 Audio extracted and sent!")
                    return await cq.answer(f"Extraction error: {err[:60]}", alert=True)

                if action == "v_tprompt":
                    return await cq.answer("💡 Reply with: .vtrim 00:15 01:30 or .vtrim 15 90", alert=True)

                dur = session.get("info", {}).get("duration", 0.0)
                recipe = session.setdefault("video_recipe", _default_video_recipe(dur))
                _toggle_video_recipe(recipe, action, dur)
                session.setdefault("action_history", []).append(action)

                # Determine active submenu
                cur_menu = "main"
                if action.startswith("v_t"):
                    cur_menu = "v_trm"
                elif action in ("v_05x", "v_075x", "v_125x", "v_15x", "v_20x"):
                    cur_menu = "v_spd"
                elif action in ("v_r90", "v_r270", "v_r180", "v_fliph", "v_flipv"):
                    cur_menu = "v_rot"
                elif action in ("v_mute", "v_vol_up", "v_vol_dn"):
                    cur_menu = "v_aud"
                elif action in ("v_bw", "v_sepia", "v_neg"):
                    cur_menu = "v_col"

                text = _build_studio_text(session, cur_menu)
                buttons = _build_studio_keyboard(session, cur_menu)
                with contextlib.suppress(MessageNotModifiedError, Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")

                return await cq.answer(f"✨ Staged: {action_label}")

            # ── PHOTO: Live Pillow Processing ──
            await cq.answer(f"⏳ Applying {action_label}…")

            session["step_counter"] += 1
            step_num = session["step_counter"]

            # Save proxy state to history for Undo
            curr_proxy = session.get("current_proxy")
            if curr_proxy:
                session.setdefault("proxy_history", []).append(curr_proxy)
            session.setdefault("action_history", []).append(action)

            try:
                new_proxy_path = str(Path(session["work_dir"]) / f"proxy_step_{step_num}.jpg")

                if not HAS_PIL:
                    session["proxy_history"].pop()
                    session["action_history"].pop()
                    return await cq.answer("Pillow is not installed.", alert=True)

                curr_file = session["current_file"]
                session.setdefault("history", []).append(curr_file)

                ext = ".webp" if action == "p_webp" else ".jpg" if action == "p_jpg" else ".png"
                out_path = str(Path(session["work_dir"]) / f"step_{step_num}{ext}")

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _process_image_sync, curr_file, out_path, action)
                session["current_file"] = out_path

                # Update proxy thumbnail
                await loop.run_in_executor(None, _generate_lightweight_thumbnail, out_path, new_proxy_path, 480)
                session["current_proxy"] = new_proxy_path

                with contextlib.suppress(Exception):
                    with Image.open(out_path) as pimg:
                        session["info"]["width"] = pimg.width
                        session["info"]["height"] = pimg.height

                text = _build_studio_text(session, "main")
                buttons = _build_studio_keyboard(session, "main")

                try:
                    await cq.edit(text, file=new_proxy_path, buttons=buttons, parse_mode="html")
                except Exception as edit_exc:
                    logger.debug(f"Live preview file update fallback: {edit_exc}")
                    with contextlib.suppress(MessageNotModifiedError, Exception):
                        await cq.edit(text, buttons=buttons, parse_mode="html")

                return await cq.answer(f"✨ {action_label} applied!")

            except Exception as exc:
                logger.error(f"Media studio action failed: {exc}")
                if session.get("proxy_history"):
                    session["current_proxy"] = session["proxy_history"].pop()
                if session.get("action_history"):
                    session["action_history"].pop()
                return await cq.answer(f"❌ Error: {str(exc)[:100]}", alert=True)


# ─── Direct Custom Video Trimming Command ────────────────────────────────────


@Friday.register_on_cmd(
    ["studiocut", "studiotrim", "scut", "strim"],
    cmd_help={
        "help": (
            "Custom cut a replied video by exact start and end times.\n"
            "Accepts seconds or MM:SS format (e.g. .vtrim 00:15 01:30 or .vtrim 10 45).\n"
            "If an interactive Media Studio is open for this video, it updates your staged cut live!"
        ),
        "example": [
            "vtrim 10 30 (replying to video)",
            "vtrim 00:15 01:45 (replying to video)",
        ],
    },
    requires_reply=True,
)
@log_errors
async def vtrim_cmd(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ <i>Please reply to a video to trim.</i>")

    mime = getattr(rm.file, "mime_type", "") or ""
    if not (rm.video or rm.video_note or mime.startswith("video/")):
        return await m.handle_message("❌ <i>Replied message is not a video.</i>")

    args = m.text.split(None, 2)[1:] if len(m.text.split()) > 1 else []
    if not args:
        return await m.handle_message(
            "❌ <i>Usage: .vtrim &lt;start&gt; &lt;end&gt; (e.g. .vtrim 00:10 01:25 or .vtrim 15 45)</i>"
        )

    t_args = args[0].split() if len(args) == 1 else args
    if len(t_args) < 2:
        return await m.handle_message(
            "❌ <i>Please provide both start and end time (e.g. .vtrim 00:10 01:25 or .vtrim 15 45).</i>"
        )

    s_val = _parse_time_str(t_args[0])
    e_val = _parse_time_str(t_args[1])

    if s_val is None or e_val is None:
        return await m.handle_message(
            "❌ <i>Invalid timestamp format. Use MM:SS or seconds (e.g. 00:15 01:30 or 15 90).</i>"
        )

    if s_val >= e_val:
        return await m.handle_message("❌ <i>Start time must be less than end time!</i>")

    # Check if an active studio session exists for this message
    active_sess = None
    for s in _SESSIONS.values():
        if s.get("chat_id") == m.chat_id and s.get("reply_to_msg_id") == rm.id and s.get("type") == "video":
            active_sess = s
            break

    if active_sess:
        dur = active_sess.get("info", {}).get("duration", 0.0)
        recipe = active_sess.setdefault("video_recipe", _default_video_recipe(dur))
        recipe["trim_start"] = s_val
        recipe["trim_end"] = e_val
        recipe["trim_active"] = True
        return await m.handle_message(
            f"✂️ <b>Custom cut staged in active studio:</b>\n"
            f"• <b>Range:</b> <code>{_format_time(s_val)}</code> ➔ <code>{_format_time(e_val)}</code> (Length: <code>{_format_time(e_val - s_val)}</code>)\n"
            f"• Tap <b>'🚀 Apply & Render'</b> in the Studio to compile!"
        )

    # Standalone quick cut
    status = await m.handle_message(f"✂️ <i>Cutting video from {_format_time(s_val)} to {_format_time(e_val)}…</i>")
    work_dir = _STUDIO_DIR / f"trim_{uuid.uuid4().hex[:6]}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        dl_path = await rm.download_media(str(work_dir / "input"))
        if not dl_path or not os.path.exists(dl_path):
            return await status.edit("❌ <i>Failed to download video.</i>")

        info = await _get_video_info(dl_path)
        out_path = str(work_dir / "trimmed.mp4")
        dur = info.get("duration", 0.0)
        recipe = _default_video_recipe(dur)
        recipe["trim_start"] = s_val
        recipe["trim_end"] = e_val
        recipe["trim_active"] = True

        await _compile_video_export(dl_path, out_path, recipe, dur, info.get("has_audio", True))

        sender = _get_active_sender_client(c)
        caption = (
            f"✂️ <b>Video Trimmed</b>\n"
            f"• <b>Cut Range:</b> <code>{_format_time(s_val)}</code> ➔ <code>{_format_time(e_val)}</code>\n"
            f"• <b>Duration:</b> <code>{_format_time(e_val - s_val)}</code>"
        )
        await sender.send_file(
            m.chat_id,
            file=out_path,
            caption=caption,
            parse_mode="html",
            reply_to=rm.id,
            supports_streaming=True,
        )
        await status.delete_if_self()
    except Exception as exc:
        logger.error(f"vtrim error: {exc}")
        await status.edit(f"❌ <i>Trim failed: {str(exc)[:100]}</i>")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
