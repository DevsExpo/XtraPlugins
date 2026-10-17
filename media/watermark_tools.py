# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import os
import shutil
import asyncio
import subprocess
from PIL import Image, ImageDraw, ImageFont

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"


def _add_watermark_to_image(img_path: str, out_path: str, text: str, pos: str = "bottom-right"):
    img = Image.open(img_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(24, int(min(img.width, img.height) * 0.05))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    t_width = bbox[2] - bbox[0]
    t_height = bbox[3] - bbox[1]

    pad = 20
    if pos == "top-left":
        x, y = pad, pad
    elif pos == "center":
        x, y = (img.width - t_width) // 2, (img.height - t_height) // 2
    else:  # bottom-right
        x, y = img.width - t_width - pad, img.height - t_height - pad

    # Semi-transparent backdrop pill
    pill_pad = 8
    draw.rounded_rectangle(
        [x - pill_pad, y - pill_pad, x + t_width + pill_pad, y + t_height + pill_pad],
        radius=8,
        fill=(0, 0, 0, 140),
    )
    # White text with subtle glow
    draw.text((x, y), text, fill=(255, 255, 255, 230), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(out_path, format="JPEG", quality=95)


@Friday.register_on_cmd(
    ["watermark", "wm"],
    cmd_help={
        "help": "Apply custom aesthetic text watermark to a replied photo or video.",
        "example": "watermark @MyChannel (reply to photo or video)\nwatermark Copyright 2026 -pos center",
    },
    requires_reply=True,
    requires_input=True,
)
async def watermark_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.photo or reply.video or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to a photo or video to watermark.")

    raw = m.user_input.strip()
    pos = "bottom-right"
    for p in ["top-left", "center", "bottom-right"]:
        if f"-pos {p}" in raw:
            pos = p
            raw = raw.replace(f"-pos {p}", "").strip()

    text = raw.strip()
    if not text:
        return await m.handle_message("⚠️ <b>Usage:</b> <code>.watermark &lt;text&gt; [-pos bottom-right|center|top-left]</code>")

    msg = await m.handle_message(f"🏷 Stamping watermark <code>{text}</code>...")
    out_dir = os.path.join("temp", "watermark")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download replied media.")

    is_video = bool(reply.video or input_file.lower().endswith((".mp4", ".mkv", ".mov", ".webm")))
    output_file = os.path.join(out_dir, f"wm_{os.path.basename(input_file)}")
    if not is_video and not output_file.lower().endswith(".jpg"):
        output_file += ".jpg"

    try:
        loop = asyncio.get_running_loop()
        if not is_video:
            await loop.run_in_executor(None, _add_watermark_to_image, input_file, output_file, text, pos)
        else:
            # Video watermark using ffmpeg drawtext filter
            ffmpeg = shutil.which("ffmpeg") or (FFMPEG_PATH if os.path.exists(FFMPEG_PATH) else "ffmpeg")
            escaped_text = text.replace(":", "\\:").replace("'", "\\'")
            x_expr = "w-tw-20" if pos == "bottom-right" else ("(w-tw)/2" if pos == "center" else "20")
            y_expr = "h-th-20" if pos == "bottom-right" else ("(h-th)/2" if pos == "center" else "20")
            drawtext_filter = f"drawtext=text='{escaped_text}':fontcolor=white@0.9:box=1:boxcolor=black@0.5:boxborderw=8:fontsize=28:x={x_expr}:y={y_expr}"

            cmd = [
                ffmpeg, "-y",
                "-i", input_file,
                "-vf", drawtext_filter,
                "-c:a", "copy",
                "-preset", "fast",
                output_file,
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await proc.communicate()

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            return await msg.edit_msg("❌ Watermark processing failed.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            output_file,
            caption=f"🏷 <b>Watermarked:</b> <code>{text}</code> (Position: <code>{pos}</code>)",
            reply_to=reply.id,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"❌ Watermark error: <code>{e}</code>")
    finally:
        for f in [input_file, output_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
