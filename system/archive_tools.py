# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import shutil
import zipfile
import tarfile
import asyncio
from typing import List
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.utils.essentials import Essentials


def _is_safe_path(base_dir: str, path: str) -> bool:
    """Zip-slip vulnerability protection."""
    base_dir = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base_dir, path))
    return os.path.commonpath([base_dir]) == os.path.commonpath([base_dir, target])


@Friday.register_on_cmd(
    ["zip"],
    cmd_help={
        "help": "Compress replied file into a ZIP archive.",
        "example": "zip [archive_name.zip] (replying to file)",
    },
    requires_reply=True,
)
async def archive_zip(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ Please reply to a file or document to zip.")

    msg = await m.handle_message("⏳ Downloading file to compress...")
    os.makedirs("temp/xtra_archives", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_archives/")

    if not download_path or not os.path.exists(download_path):
        return await msg.edit_msg("❌ Failed to download target file.")

    archive_name = m.user_input.strip() if m.user_input else ""
    if not archive_name:
        archive_name = os.path.splitext(os.path.basename(download_path))[0] + ".zip"
    elif not archive_name.endswith(".zip"):
        archive_name += ".zip"

    zip_path = os.path.join("temp/xtra_archives", archive_name)

    try:
        await msg.edit_msg(f"📦 Compressing into <code>{archive_name}</code>...")

        def _do_zip():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(download_path, arcname=os.path.basename(download_path))

        await asyncio.get_running_loop().run_in_executor(None, _do_zip)

        orig_size = Essentials.humanbytes(os.path.getsize(download_path))
        zip_size = Essentials.humanbytes(os.path.getsize(zip_path))

        await msg.edit_msg("📤 Uploading ZIP archive...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            zip_path,
            caption=(
                f"📦 <b>Archive Created:</b> <code>{archive_name}</code>\n"
                f"<b>• Original:</b> <code>{orig_size}</code>\n"
                f"<b>• Compressed:</b> <code>{zip_size}</code>"
            ),
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Zip compression failed: <code>{e}</code>")
    finally:
        for p in (download_path, zip_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["unzip"],
    cmd_help={
        "help": "Safely extract contents of a replied ZIP archive.",
        "example": "unzip (replying to .zip file)",
    },
    requires_reply=True,
)
async def archive_unzip(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ Please reply to a ZIP file to extract.")

    msg = await m.handle_message("⏳ Downloading ZIP archive...")
    os.makedirs("temp/xtra_archives", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_archives/")

    if not download_path or not zipfile.is_zipfile(download_path):
        if download_path and os.path.exists(download_path):
            os.remove(download_path)
        return await msg.edit_msg("❌ Replied file is not a valid ZIP archive.")

    extract_dir = os.path.join("temp/xtra_archives", f"extract_{m.id}")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        await msg.edit_msg("🔓 Extracting archive files...")

        def _do_unzip() -> List[str]:
            extracted_files = []
            with zipfile.ZipFile(download_path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    # Zip slip security validation
                    if not _is_safe_path(extract_dir, member.filename):
                        continue
                    target_file = zf.extract(member, extract_dir)
                    extracted_files.append(target_file)
            return extracted_files

        extracted = await asyncio.get_running_loop().run_in_executor(None, _do_unzip)

        if not extracted:
            return await msg.edit_msg("⚠️ Archive was empty or contained no safe files to extract.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        total_extracted = len(extracted)

        # If 1-5 files, upload them directly
        if total_extracted <= 5:
            await msg.edit_msg(f"📤 Uploading {total_extracted} extracted file(s)...")
            for f in extracted:
                if os.path.isfile(f):
                    await c.send_file(
                        target_chat,
                        f,
                        caption=f"📄 <code>{os.path.basename(f)}</code> ({Essentials.humanbytes(os.path.getsize(f))})",
                        reply_to=m.id,
                    )
            try:
                await msg.delete()

            except Exception:
                pass
        else:
            # Re-upload the top 5 and give a full manifest
            await msg.edit_msg(f"📤 Archive contains {total_extracted} files. Uploading first 5 files...")
            for f in extracted[:5]:
                if os.path.isfile(f):
                    await c.send_file(
                        target_chat,
                        f,
                        caption=f"📄 <code>{os.path.basename(f)}</code> ({Essentials.humanbytes(os.path.getsize(f))})",
                        reply_to=m.id,
                    )
            manifest = "\n".join(
                [
                    f"• <code>{os.path.relpath(f, extract_dir)}</code> ({Essentials.humanbytes(os.path.getsize(f))})"
                    for f in extracted[:25]
                ]
            )
            await msg.edit_msg(
                f"✅ <b>Extracted {total_extracted} files.</b> Top entries:\n{manifest}\n"
                f"<i>(Uploaded first 5 files to avoid flood)</i>"
            )
    except Exception as e:
        await msg.edit_msg(f"❌ Extraction error: <code>{e}</code>")
    finally:
        if os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass
        if os.path.exists(extract_dir):
            try:
                shutil.rmtree(extract_dir)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["ziplist", "archivelist"],
    cmd_help={
        "help": "Inspect and list all contents of an archive (.zip, .tar, .tar.gz) without extracting.",
        "example": "ziplist (replying to archive)",
    },
    requires_reply=True,
)
async def archive_list(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ Please reply to an archive file (.zip, .tar, .tar.gz).")

    msg = await m.handle_message("🔍 Inspecting archive structure...")
    os.makedirs("temp/xtra_archives", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_archives/")

    if not download_path or not os.path.exists(download_path):
        return await msg.edit_msg("❌ Failed to download archive.")

    try:
        entries = []
        total_uncompressed = 0

        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path, "r") as zf:
                for info in zf.infolist():
                    if not info.is_dir():
                        total_uncompressed += info.file_size
                        entries.append(f"• <code>{info.filename}</code> ({Essentials.humanbytes(info.file_size)})")
        elif tarfile.is_tarfile(download_path):
            with tarfile.open(download_path, "r:*") as tf:
                for member in tf.getmembers():
                    if member.isfile():
                        total_uncompressed += member.size
                        entries.append(f"• <code>{member.name}</code> ({Essentials.humanbytes(member.size)})")
        else:
            return await msg.edit_msg("❌ Unsupported archive format. Supported: .zip, .tar, .tar.gz, .tgz")

        archive_size = Essentials.humanbytes(os.path.getsize(download_path))
        uncomp_size = Essentials.humanbytes(total_uncompressed)
        total_count = len(entries)

        header = (
            f"📦 <b>Archive Manifest:</b> <code>{os.path.basename(download_path)}</code>\n"
            f"<b>• Files:</b> <code>{total_count}</code>\n"
            f"<b>• Archive Size:</b> <code>{archive_size}</code>\n"
            f"<b>• Uncompressed:</b> <code>{uncomp_size}</code>\n\n"
        )

        display_entries = entries[:30]
        body = "\n".join(display_entries)
        if total_count > 30:
            body += f"\n<i>...and {total_count - 30} more file(s)</i>"

        await msg.edit_msg(header + body)
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to read archive: <code>{e}</code>")
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["targz", "tar"],
    cmd_help={
        "help": "Compress replied file into a TAR.GZ archive.",
        "example": "targz [name.tar.gz] (replying to file)",
    },
    requires_reply=True,
)
async def archive_tar(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file:
        return await m.handle_message("❌ Please reply to a file to compress.")

    msg = await m.handle_message("⏳ Downloading file...")
    os.makedirs("temp/xtra_archives", exist_ok=True)
    download_path = await rm.download_media("temp/xtra_archives/")

    if not download_path or not os.path.exists(download_path):
        return await msg.edit_msg("❌ Failed to download target file.")

    archive_name = m.user_input.strip() if m.user_input else ""
    if not archive_name:
        archive_name = os.path.splitext(os.path.basename(download_path))[0] + ".tar.gz"
    elif not archive_name.endswith((".tar.gz", ".tgz")):
        archive_name += ".tar.gz"

    tar_path = os.path.join("temp/xtra_archives", archive_name)

    try:
        await msg.edit_msg(f"📦 Compressing into <code>{archive_name}</code>...")

        def _do_tar():
            with tarfile.open(tar_path, "w:gz") as tf:
                tf.add(download_path, arcname=os.path.basename(download_path))

        await asyncio.get_running_loop().run_in_executor(None, _do_tar)

        orig_size = Essentials.humanbytes(os.path.getsize(download_path))
        tar_size = Essentials.humanbytes(os.path.getsize(tar_path))

        await msg.edit_msg("📤 Uploading TAR.GZ archive...")
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            tar_path,
            caption=(
                f"📦 <b>Archive Created:</b> <code>{archive_name}</code>\n"
                f"<b>• Original:</b> <code>{orig_size}</code>\n"
                f"<b>• Compressed:</b> <code>{tar_size}</code>"
            ),
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Tar compression failed: <code>{e}</code>")
    finally:
        for p in (download_path, tar_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
