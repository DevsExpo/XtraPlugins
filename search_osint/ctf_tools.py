# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import re
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.utils.essentials import Essentials

try:
    from PIL import Image, ExifTags

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

MAGIC_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "PNG Image"),
    (b"\xff\xd8\xff", "JPEG Image"),
    (b"GIF87a", "GIF87a Image"),
    (b"GIF89a", "GIF89a Image"),
    (b"%PDF-", "PDF Document"),
    (b"PK\x03\x04", "ZIP / APK / DOCX Archive"),
    (b"\x1f\x8b\x08", "GZIP Compressed Archive"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip Archive"),
    (b"RIFF", "RIFF (WebP / WAV / AVI)"),
    (b"\x7fELF", "Linux ELF Executable"),
    (b"MZ", "Windows PE Executable / DLL"),
]


def _detect_magic(data: bytes) -> str:
    for sig, desc in MAGIC_SIGNATURES:
        if data.startswith(sig):
            return desc
    return "Generic Binary"


@Friday.register_on_cmd(
    ["ctfinfo", "exif", "stego", "forensics"],
    cmd_help={
        "help": "Extract EXIF metadata, GPS tags, detect file magic bytes, and scan for hidden CTF flags or appended payloads.",
        "example": "ctfinfo (replying to photo/document)",
    },
    requires_reply=True,
)
async def ctf_media_forensics(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ Please reply to a photo, document, or media file.")

    msg = await m.handle_message("🔬 Inspecting binary forensics & EXIF headers...")
    os.makedirs("temp/xtra_ctf", exist_ok=True)
    file_path = await rm.download_media("temp/xtra_ctf/")

    if not file_path or not os.path.exists(file_path):
        return await msg.edit_msg("❌ Failed to download target file.")

    try:
        with open(file_path, "rb") as f:
            raw_data = f.read()

        file_size = Essentials.humanbytes(len(raw_data))
        detected_type = _detect_magic(raw_data)
        filename = os.path.basename(file_path)

        # 1. Check EXIF metadata
        exif_entries = []
        if HAS_PIL and detected_type.startswith(("JPEG", "PNG", "RIFF")):
            try:
                with Image.open(file_path) as im:
                    exif_data = im.getexif()
                    if exif_data:
                        for tag_id, val in exif_data.items():
                            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                            if str(val).strip():
                                exif_entries.append(f"• <b>{tag_name}:</b> <code>{str(val)[:80]}</code>")
            except Exception:
                pass

        # 2. Check for hidden appended payload (after JPEG EOI 0xFFD9 or PNG IEND)
        appended_warning = ""
        if raw_data.startswith(b"\xff\xd8"):
            eoi_idx = raw_data.rfind(b"\xff\xd9")
            if eoi_idx != -1 and (eoi_idx + 2) < len(raw_data):
                extra_bytes = len(raw_data) - (eoi_idx + 2)
                appended_warning = (
                    f"\n⚠️ <b>Steganography Alert:</b> <code>{extra_bytes} bytes</code> appended after JPEG EOI marker!"
                )
        elif raw_data.startswith(b"\x89PNG"):
            iend_idx = raw_data.rfind(b"IEND\xaeB`\x82")
            if iend_idx != -1 and (iend_idx + 8) < len(raw_data):
                extra_bytes = len(raw_data) - (iend_idx + 8)
                appended_warning = (
                    f"\n⚠️ <b>Steganography Alert:</b> <code>{extra_bytes} bytes</code> appended after PNG IEND chunk!"
                )

        # 3. Scan for strings matching CTF flags (flag{...}, ctf{...})
        flag_matches = re.findall(rb"(?:flag|ctf|FRIDAY)\{[a-zA-Z0-9_\-\.\@\!]+\}", raw_data, re.IGNORECASE)
        found_flags = list(set([f.decode("utf-8", errors="ignore") for f in flag_matches]))

        flags_block = ""
        if found_flags:
            flags_block = "\n🚩 <b>Discovered Flags:</b>\n" + "\n".join([f"• <code>{fl}</code>" for fl in found_flags])

        exif_block = ""
        if exif_entries:
            exif_block = "\n<b>📸 EXIF Metadata:</b>\n" + "\n".join(exif_entries[:15])
        else:
            exif_block = "\n<i>(No standard EXIF tags found)</i>"

        report = (
            f"🔬 <b>Forensic Analysis:</b> <code>{filename}</code>\n"
            f"<b>• File Size:</b> <code>{file_size}</code>\n"
            f"<b>• Magic Signature:</b> <code>{detected_type}</code>"
            f"{appended_warning}"
            f"{flags_block}\n"
            f"{exif_block}"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Forensic analysis error: <code>{e}</code>")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
