# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import math
import shutil
import zipfile
import tarfile
import subprocess
from typing import List
from PIL import Image, ImageOps

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

BG_COLORS = {
    "black": (15, 15, 18),
    "white": (250, 250, 252),
    "dark": (28, 30, 38),
    "midnight": (15, 23, 42),
    "rose": (40, 20, 30),
    "emerald": (10, 35, 28),
    "slate": (51, 65, 85),
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}


def _create_styled_collage(
    image_paths: List[str],
    out_path: str,
    layout: str = "grid",
    bg_key: str = "dark",
    padding: int = 16,
) -> None:
    """
    Create custom multi-image collages with Pillow.
    """
    opened = []
    for p in image_paths:
        try:
            im = Image.open(p).convert("RGB")
            opened.append(im)
        except Exception:
            pass

    if not opened:
        raise ValueError("Could not parse or open any valid image files.")

    num_imgs = len(opened)
    cell_size = 512
    bg_color = BG_COLORS.get(bg_key, BG_COLORS["dark"])

    # Polaroid layout: adds white card borders and classic bottom margin
    if layout == "polaroid":
        processed = []
        p_border = 18
        p_bottom = 60
        for img in opened:
            fitted = ImageOps.fit(img, (cell_size, cell_size), method=Image.Resampling.LANCZOS)
            p_card = Image.new("RGB", (cell_size + (p_border * 2), cell_size + p_border + p_bottom), (255, 255, 255))
            p_card.paste(fitted, (p_border, p_border))
            processed.append(p_card)

        cols = math.ceil(math.sqrt(num_imgs))
        rows = math.ceil(num_imgs / cols)
        card_w, card_h = processed[0].size

        canvas_w = (cols * card_w) + (padding * (cols + 1))
        canvas_h = (rows * card_h) + (padding * (rows + 1))
        collage = Image.new("RGB", (canvas_w, canvas_h), bg_color)

        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= num_imgs:
                    break
                x = padding + c * (card_w + padding)
                y = padding + r * (card_h + padding)
                collage.paste(processed[idx], (x, y))
                idx += 1

        collage.save(out_path, "JPEG", quality=92, optimize=True)
        for im in opened + processed:
            im.close()
        return

    # Standard layouts: grid, row, column
    standardized = []
    for img in opened:
        fitted = ImageOps.fit(img, (cell_size, cell_size), method=Image.Resampling.LANCZOS)
        standardized.append(fitted)

    if layout == "row":
        cols, rows = num_imgs, 1
    elif layout == "column":
        cols, rows = 1, num_imgs
    else:
        cols = math.ceil(math.sqrt(num_imgs))
        rows = math.ceil(num_imgs / cols)

    canvas_w = (cols * cell_size) + (padding * (cols + 1))
    canvas_h = (rows * cell_size) + (padding * (rows + 1))

    collage = Image.new("RGB", (canvas_w, canvas_h), bg_color)

    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= num_imgs:
                break
            x = padding + c * (cell_size + padding)
            y = padding + r * (cell_size + padding)
            collage.paste(standardized[idx], (x, y))
            idx += 1

    collage.save(out_path, "JPEG", quality=92, optimize=True)
    for im in opened + standardized:
        im.close()


def _extract_images_from_zip(archive_path: str, extract_dir: str) -> List[str]:
    """Safely extract all images from a zip archive with Zip-Slip protection."""
    image_paths = []
    with zipfile.ZipFile(archive_path, "r") as z:
        for member in z.infolist():
            ext = os.path.splitext(member.filename)[1].lower()
            if ext in IMAGE_EXTENSIONS and not member.is_dir():
                clean_name = os.path.basename(member.filename)
                target = os.path.join(extract_dir, clean_name)
                with z.open(member) as source, open(target, "wb") as outfile:
                    shutil.copyfileobj(source, outfile)
                image_paths.append(target)
    return image_paths


def _extract_frames_from_video(video_path: str, out_dir: str, num_frames: int = 4) -> List[str]:
    """Extract multiple evenly spaced frames from a video file locally using FFmpeg."""
    frames = []
    if not shutil.which("ffmpeg"):
        return frames

    try:
        # Get video duration using ffprobe
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = float(res.stdout.strip()) if res.stdout.strip() else 10.0
    except Exception:
        duration = 10.0

    interval = max(0.5, duration / (num_frames + 1))
    for i in range(1, num_frames + 1):
        timestamp = round(i * interval, 2)
        frame_file = os.path.join(out_dir, f"frame_{i}.jpg")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            video_path,
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-loglevel",
            "error",
            frame_file,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(frame_file) and os.path.getsize(frame_file) > 1000:
                frames.append(frame_file)
        except Exception:
            pass

    return frames


@Friday.register_on_cmd(
    ["collage", "grid", "photogrid"],
    cmd_help={
        "help": "Create an image collage locally on machine from photos, albums, videos, or zip archives.",
        "example": "collage (reply to photo or album)\ncollage 4 (takes last 4 photos in chat)\ncollage (reply to .zip file)\ncollage (reply to video for storyboard)\nOptions: -layout [grid|row|column|polaroid], -bg [dark|white|midnight|rose], -pad <px>",
    },
)
async def make_collage(c: Client, m: Message):
    raw = (m.user_input or "").lower().strip()
    layout = "grid"
    bg = "dark"
    padding = 16
    fetch_count = 0

    # Parse count from input (e.g. .collage 4 or .collage 6)
    tokens = raw.split()
    for tok in tokens:
        if tok.isdigit():
            fetch_count = max(2, min(16, int(tok)))
            break

    if "-layout" in raw:
        parts = raw.split("-layout")
        layout_cand = parts[1].strip().split()[0]
        if layout_cand in ["grid", "row", "column", "col", "polaroid"]:
            layout = "column" if layout_cand == "col" else layout_cand

    if "-bg" in raw:
        parts = raw.split("-bg")
        bg_cand = parts[1].strip().split()[0]
        if bg_cand in BG_COLORS:
            bg = bg_cand

    if "-pad" in raw:
        try:
            parts = raw.split("-pad")
            padding = max(0, min(50, int(parts[1].strip().split()[0])))
        except Exception:
            pass

    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)

    msg = await m.handle_message(f"🖼 Collecting media for local collage (Layout: <code>{layout.title()}</code>)...")
    temp_dir = os.path.join("temp", f"collage_{m.id}")
    os.makedirs(temp_dir, exist_ok=True)

    collected_images: List[str] = []

    try:
        chat_target = m.chat_id or getattr(m.chat, "id", None)

        # SCENARIO 1: Replied to a Telegram Media Album (grouped_id)
        if rm and getattr(rm, "grouped_id", None):
            target_gid = rm.grouped_id
            async for chat_msg in c.iter_messages(chat_target, limit=20):
                if getattr(chat_msg, "grouped_id", None) == target_gid and chat_msg.media:
                    fpath = await chat_msg.download_media(temp_dir)
                    if fpath and os.path.exists(fpath):
                        ext = os.path.splitext(fpath)[1].lower()
                        if ext in IMAGE_EXTENSIONS:
                            collected_images.append(fpath)
                        elif ext in {".mp4", ".mov", ".mkv", ".webm"}:
                            frames = _extract_frames_from_video(fpath, temp_dir, num_frames=2)
                            collected_images.extend(frames)

        # SCENARIO 2: Replied to a single message with media (photo, video, zip)
        elif rm and rm.media:
            downloaded_media = await rm.download_media(temp_dir)
            if downloaded_media and os.path.exists(downloaded_media):
                ext = os.path.splitext(downloaded_media)[1].lower()

                # Case 2A: Zip / Archive file (e.g. UpdateP.zip)
                if ext == ".zip":
                    extracted = _extract_images_from_zip(downloaded_media, temp_dir)
                    collected_images.extend(extracted)
                elif ext in {".tar", ".gz", ".tgz"}:
                    try:
                        with tarfile.open(downloaded_media, "r:*") as t:
                            for member in t.getmembers():
                                mext = os.path.splitext(member.name)[1].lower()
                                if mext in IMAGE_EXTENSIONS and member.isfile():
                                    t.extract(member, temp_dir)
                                    collected_images.append(os.path.join(temp_dir, member.name))
                    except Exception:
                        pass

                # Case 2B: Video file (extract storyboard frames)
                elif ext in {".mp4", ".mov", ".mkv", ".webm"}:
                    frames = _extract_frames_from_video(downloaded_media, temp_dir, num_frames=fetch_count or 4)
                    collected_images.extend(frames)

                # Case 2C: Standard image or sticker
                elif ext in IMAGE_EXTENSIONS:
                    collected_images.append(downloaded_media)

                    # If user requested a count or replied message had history, gather previous photos
                    if fetch_count > 1:
                        async for prev_msg in c.iter_messages(chat_target, max_id=rm.id, limit=30):
                            if prev_msg.photo or (
                                prev_msg.file
                                and prev_msg.file.mime_type
                                and prev_msg.file.mime_type.startswith("image/")
                            ):
                                pf = await prev_msg.download_media(temp_dir)
                                if pf and os.path.exists(pf):
                                    collected_images.append(pf)
                                if len(collected_images) >= fetch_count:
                                    break

        # SCENARIO 3: No direct media reply, or user requested `.collage <count>` from recent chat history
        elif fetch_count > 0 or not rm:
            limit_search = fetch_count or 4
            async for chat_msg in c.iter_messages(chat_target, limit=40):
                if chat_msg.id == m.id:
                    continue
                if chat_msg.photo or (
                    chat_msg.file and chat_msg.file.mime_type and chat_msg.file.mime_type.startswith("image/")
                ):
                    pf = await chat_msg.download_media(temp_dir)
                    if pf and os.path.exists(pf):
                        collected_images.append(pf)
                elif chat_msg.video or (
                    chat_msg.file and chat_msg.file.mime_type and chat_msg.file.mime_type.startswith("video/")
                ):
                    vf = await chat_msg.download_media(temp_dir)
                    if vf and os.path.exists(vf):
                        frames = _extract_frames_from_video(vf, temp_dir, num_frames=2)
                        collected_images.extend(frames)

                if len(collected_images) >= limit_search:
                    break

        if not collected_images:
            return await msg.edit_msg(
                "❌ <b>No images found to collage!</b>\n"
                "• Reply to a photo, sticker, or album.\n"
                "• Reply to a <code>.zip</code> file containing images (e.g. <code>UpdateP.zip</code>).\n"
                "• Reply to a video to create a storyboard collage.\n"
                "• Or type <code>.collage 4</code> to gather recent chat photos."
            )

        # Deduplicate and limit
        valid_paths = [p for p in collected_images if os.path.exists(p)][:16]

        if len(valid_paths) == 1:
            # Creative mirror reflection if only 1 photo provided
            im = Image.open(valid_paths[0])
            m_path = os.path.join(temp_dir, f"mirror_{m.id}.jpg")
            im.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(m_path)
            valid_paths.append(m_path)
            im.close()

        out_collage = os.path.join(temp_dir, f"collage_{m.id}.jpg")
        _create_styled_collage(valid_paths, out_collage, layout=layout, bg_key=bg, padding=padding)

        reply_target_id = rm.id if rm else m.id
        await c.send_file(
            chat_target,
            out_collage,
            caption=f"🖼 <b>Collage Created</b> ({len(valid_paths)} images, {layout.title()})",
            reply_to=reply_target_id,
        )

        try:
            await msg.delete()
        except Exception:
            pass

    except Exception as e:
        await msg.edit_msg(f"❌ Collage synthesis error: <code>{e}</code>")
    finally:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
