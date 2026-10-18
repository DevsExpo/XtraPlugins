# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import asyncio
import logging
from typing import Optional, List, Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.utils.essentials import Essentials
from telethon import Button

logger = logging.getLogger("friday.pdf_tools")

try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _check_dependencies():
    if not HAS_FITZ and not HAS_PIL:
        raise RuntimeError("PyMuPDF or Pillow is required for PDF tools.")


def _parse_page_selection(query: str, max_pages: int) -> List[int]:
    """Parse 1-indexed page queries like '1-3, 5, 8-10' into sorted 0-indexed integer list."""
    selected = set()
    parts = [p.strip() for p in query.replace(" ", "").split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            start_s, end_s = p.split("-", 1)
            try:
                start = max(1, min(max_pages, int(start_s)))
                end = max(1, min(max_pages, int(end_s)))
                for n in range(min(start, end), max(start, end) + 1):
                    selected.add(n - 1)
            except ValueError:
                continue
        else:
            try:
                n = int(p)
                if 1 <= n <= max_pages:
                    selected.add(n - 1)
            except ValueError:
                continue
    return sorted(list(selected))


async def _download_replied_pdf(m: Message, out_dir: str = "temp/xtra_pdf") -> Tuple[Optional[str], Optional[str]]:
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file or not (rm.file.name and rm.file.name.lower().endswith(".pdf")):
        return None, None
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = await rm.download_media(out_dir + "/")
    filename = getattr(rm.file, "name", "document.pdf")
    return pdf_path, filename


def _text_to_pdf(text: str, out_pdf_path: str) -> None:
    """Render multi-line text into a clean paginated PDF document."""
    page_width, page_height = 595, 842  # A4 standard at 72 DPI
    if HAS_FITZ:
        doc = fitz.open()
        lines = text.splitlines()
        lines_per_page = 42
        margin_x = 50
        margin_y = 60
        line_height = 16

        for i in range(0, max(1, len(lines)), lines_per_page):
            chunk = lines[i : i + lines_per_page]
            page = doc.new_page(width=page_width, height=page_height)
            # Header line
            page.draw_line(
                fitz.Point(margin_x, 40), fitz.Point(page_width - margin_x, 40), color=(0.16, 0.5, 0.72), width=2
            )
            y = margin_y
            for line in chunk:
                page.insert_text(fitz.Point(margin_x, y), line, fontsize=10, color=(0.15, 0.15, 0.15))
                y += line_height
        doc.save(out_pdf_path, deflate=True)
        doc.close()
    elif HAS_PIL:
        p_w, p_h = 1240, 1754
        margin = 80
        font = ImageFont.load_default()
        line_height = 28
        lines = text.splitlines()
        lines_per_page = (p_h - (2 * margin)) // line_height
        pages = []
        for i in range(0, max(1, len(lines)), lines_per_page):
            chunk = lines[i : i + lines_per_page]
            img = Image.new("RGB", (p_w, p_h), "white")
            draw = ImageDraw.Draw(img)
            draw.rectangle([(margin, 50), (p_w - margin, 54)], fill=(41, 128, 185))
            y = margin
            for line in chunk:
                draw.text((margin, y), line, fill=(30, 30, 30), font=font)
                y += line_height
            pages.append(img)
        if pages:
            pages[0].save(out_pdf_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])


# ==========================================
# Core Conversion Commands
# ==========================================


@Friday.register_on_cmd(
    ["topdf", "pdf"],
    cmd_help={
        "help": "Convert text or replied image/document to a formatted PDF file.",
        "example": "topdf My document text here\n(or reply to an image with .topdf)",
    },
)
async def create_pdf(c: Client, m: Message):
    _check_dependencies()
    msg = await m.handle_message("📄 Generating PDF document...")
    os.makedirs("temp/xtra_pdf", exist_ok=True)
    out_pdf = f"temp/xtra_pdf/document_{m.id}.pdf"

    text_input = (m.user_input or "").strip()
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)

    try:
        if rm and (rm.photo or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("image/"))):
            await msg.edit_msg("🖼 Downloading replied image...")
            img_path = await rm.download_media("temp/xtra_pdf/")
            if img_path and os.path.exists(img_path):

                def _conv():
                    if HAS_FITZ:
                        doc = fitz.open()
                        img_doc = fitz.open(img_path)
                        pdf_bytes = img_doc.convert_to_pdf()
                        img_doc.close()
                        img_pdf = fitz.open("pdf", pdf_bytes)
                        doc.insert_pdf(img_pdf)
                        img_pdf.close()
                        doc.save(out_pdf, deflate=True)
                        doc.close()
                    elif HAS_PIL:
                        with Image.open(img_path) as im:
                            im.convert("RGB").save(out_pdf, "PDF", resolution=100.0)

                await asyncio.get_running_loop().run_in_executor(None, _conv)
                if os.path.exists(img_path):
                    os.remove(img_path)
            else:
                return await msg.edit_msg("❌ Failed to download replied image.")
        else:
            if not text_input and rm and (rm.text or rm.caption):
                text_input = rm.text or rm.caption
            if not text_input:
                return await msg.edit_msg("❌ Please provide text or reply to an image/text to convert to PDF.")
            await asyncio.get_running_loop().run_in_executor(None, lambda: _text_to_pdf(text_input, out_pdf))

        if not os.path.exists(out_pdf):
            return await msg.edit_msg("❌ PDF creation failed.")

        pdf_size = Essentials.humanbytes(os.path.getsize(out_pdf))
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_pdf,
            caption=f"📄 <b>PDF Created Successfully</b>\n<b>Size:</b> <code>{pdf_size}</code>",
            reply_to=m.id,
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to create PDF: <code>{e}</code>")
    finally:
        if os.path.exists(out_pdf):
            try:
                os.remove(out_pdf)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["imgtopdf", "imagetopdf", "jpgtopdf"],
    cmd_help={
        "help": "Convert replied image into a high-quality PDF document.",
        "example": "imgtopdf (replying to photo)",
    },
    requires_reply=True,
)
async def image_to_pdf(c: Client, m: Message):
    return await create_pdf(c, m)


# ==========================================
# iLovePDF Operations (Merge, Split, Compress)
# ==========================================


@Friday.register_on_cmd(
    ["pdfcompress", "compresspdf"],
    cmd_help={
        "help": "Compress and optimize PDF file size using stream deflation and object garbage collection.",
        "example": "pdfcompress (replying to PDF)",
    },
    requires_reply=True,
)
async def compress_pdf(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🗜 Compressing and optimizing PDF...")
    out_pdf = f"temp/xtra_pdf/compressed_{os.path.basename(pdf_path)}"

    try:
        orig_size = os.path.getsize(pdf_path)

        def _compress():
            doc = fitz.open(pdf_path)
            doc.save(out_pdf, garbage=4, deflate=True, clean=True)
            doc.close()

        await asyncio.get_running_loop().run_in_executor(None, _compress)
        new_size = os.path.getsize(out_pdf)
        saved = max(0, orig_size - new_size)
        pct = (saved / orig_size * 100) if orig_size else 0

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        report = (
            f"🗜 <b>PDF Compressed Successfully</b>\n\n"
            f"<b>• Original:</b> <code>{Essentials.humanbytes(orig_size)}</code>\n"
            f"<b>• Optimized:</b> <code>{Essentials.humanbytes(new_size)}</code>\n"
            f"<b>• Reduction:</b> <code>{pct:.1f}% ({Essentials.humanbytes(saved)} saved)</code>"
        )
        await c.send_file(target_chat, out_pdf, caption=report, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to compress PDF: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["pdfsplit", "splitpdf"],
    cmd_help={
        "help": "Split a PDF file by page range (e.g. 1-5, 8-12) or specific pages.",
        "example": "pdfsplit 1-3 (replying to PDF)\npdfsplit 2,4,6",
    },
    requires_reply=True,
    requires_input=True,
)
async def split_pdf(c: Client, m: Message):
    query = m.user_input.strip()
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message(f"✂️ Splitting PDF pages <code>{query}</code>...")
    out_pdf = f"temp/xtra_pdf/split_{os.path.basename(pdf_path)}"

    try:

        def _split():
            doc = fitz.open(pdf_path)
            selected = _parse_page_selection(query, doc.page_count)
            if not selected:
                doc.close()
                raise ValueError("No valid pages found in the requested range.")
            doc.select(selected)
            doc.save(out_pdf, deflate=True)
            page_count = doc.page_count
            doc.close()
            return page_count

        count = await asyncio.get_running_loop().run_in_executor(None, _split)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        report = f"✂️ <b>PDF Split Completed</b>\n<b>Pages Extracted:</b> <code>{count}</code>\n<b>Range:</b> <code>{query}</code>"
        await c.send_file(target_chat, out_pdf, caption=report, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to split PDF: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["pdfextract"],
    cmd_help={
        "help": "Extract specific pages from a PDF into a new document.",
        "example": "pdfextract 1,3,5 (replying to PDF)",
    },
    requires_reply=True,
    requires_input=True,
)
async def extract_pdf_pages(c: Client, m: Message):
    return await split_pdf(c, m)


@Friday.register_on_cmd(
    ["pdfdelete", "pdfremove"],
    cmd_help={
        "help": "Delete specified pages from a PDF document.",
        "example": "pdfdelete 2,4 (replying to PDF)",
    },
    requires_reply=True,
    requires_input=True,
)
async def delete_pdf_pages(c: Client, m: Message):
    query = m.user_input.strip()
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message(f"🗑 Deleting pages <code>{query}</code> from PDF...")
    out_pdf = f"temp/xtra_pdf/deleted_{os.path.basename(pdf_path)}"

    try:

        def _del():
            doc = fitz.open(pdf_path)
            to_delete = _parse_page_selection(query, doc.page_count)
            if not to_delete:
                doc.close()
                raise ValueError("No matching pages found to delete.")
            if len(to_delete) >= doc.page_count:
                doc.close()
                raise ValueError("Cannot delete all pages of the document.")
            doc.delete_pages(to_delete)
            doc.save(out_pdf, deflate=True)
            rem = doc.page_count
            doc.close()
            return len(to_delete), rem

        deleted_cnt, remaining_cnt = await asyncio.get_running_loop().run_in_executor(None, _del)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        report = (
            f"🗑 <b>PDF Pages Deleted</b>\n\n"
            f"<b>• Pages Removed:</b> <code>{deleted_cnt}</code> (<code>{query}</code>)\n"
            f"<b>• Pages Remaining:</b> <code>{remaining_cnt}</code>"
        )
        await c.send_file(target_chat, out_pdf, caption=report, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to delete pages: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@Friday.register_on_cmd(
    ["pdfmerge", "mergepdf"],
    cmd_help={
        "help": "Merge multiple PDF documents into a single master document.",
        "example": "pdfmerge (replying to a PDF message that replied to another PDF, or specify paths)",
    },
    requires_reply=True,
)
async def merge_pdf(c: Client, m: Message):
    # Retrieve replied message and parent message if chained
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file or not (rm.file.name and rm.file.name.lower().endswith(".pdf")):
        return await m.handle_message("❌ Please reply to a PDF file to begin merging.")

    msg = await m.handle_message("📚 Preparing to merge PDFs...")
    os.makedirs("temp/xtra_pdf", exist_ok=True)
    pdf1 = await rm.download_media("temp/xtra_pdf/")

    # Check if replied message is also a reply to a PDF
    parent_rm = await rm.get_reply_message() if hasattr(rm, "get_reply_message") else None
    pdf2 = None
    if parent_rm and parent_rm.file and parent_rm.file.name and parent_rm.file.name.lower().endswith(".pdf"):
        pdf2 = await parent_rm.download_media("temp/xtra_pdf/")

    out_pdf = f"temp/xtra_pdf/merged_{m.id}.pdf"
    try:
        if not pdf2:
            return await msg.edit_msg(
                "ℹ️ To merge, reply with <code>.pdfmerge</code> to a PDF that itself is a reply to another PDF, or use chained messages."
            )

        def _merge():
            doc1 = fitz.open(pdf2)
            doc2 = fitz.open(pdf1)
            doc1.insert_pdf(doc2)
            doc1.save(out_pdf, deflate=True)
            total = doc1.page_count
            doc1.close()
            doc2.close()
            return total

        total_pages = await asyncio.get_running_loop().run_in_executor(None, _merge)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        report = f"📚 <b>PDFs Merged Successfully</b>\n<b>Total Pages:</b> <code>{total_pages}</code>\n<b>Size:</b> <code>{Essentials.humanbytes(os.path.getsize(out_pdf))}</code>"
        await c.send_file(target_chat, out_pdf, caption=report, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Merge failed: <code>{e}</code>")
    finally:
        for p in (pdf1, pdf2, out_pdf):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


# ==========================================
# Rendering & Extraction (Images, Text)
# ==========================================


@Friday.register_on_cmd(
    ["pdftoimg", "pdf2img", "pdfimages"],
    cmd_help={
        "help": "Convert PDF pages into high-resolution images or extract page 1.",
        "example": "pdftoimg (extracts page 1)\npdftoimg 1-3\npdftoimg all",
    },
    requires_reply=True,
)
async def pdf_to_images(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🖼 Rendering PDF pages to images (150 DPI)...")
    out_dir = f"temp/xtra_pdf/rendered_{m.id}"
    os.makedirs(out_dir, exist_ok=True)
    rendered_files = []

    try:
        user_arg = (m.user_input or "1").strip().lower()

        def _render():
            doc = fitz.open(pdf_path)
            max_p = doc.page_count
            if user_arg == "all":
                pages_to_render = list(range(min(10, max_p)))
            elif "-" in user_arg or "," in user_arg:
                pages_to_render = _parse_page_selection(user_arg, max_p)[:10]
            else:
                try:
                    p_num = max(1, min(max_p, int(user_arg)))
                    pages_to_render = [p_num - 1]
                except ValueError:
                    pages_to_render = [0]

            files = []
            for p_idx in pages_to_render:
                page = doc[p_idx]
                pix = page.get_pixmap(dpi=150)
                out_path = os.path.join(out_dir, f"page_{p_idx + 1}.png")
                pix.save(out_path)
                files.append((out_path, p_idx + 1))
            doc.close()
            return files

        rendered_files = await asyncio.get_running_loop().run_in_executor(None, _render)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        for f_path, page_num in rendered_files:
            await c.send_file(
                target_chat,
                f_path,
                caption=f"📄 <b>{filename}</b> — Page {page_num}",
                reply_to=m.id,
            )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to render images: <code>{e}</code>")
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
        for f_path, _ in rendered_files:
            if os.path.exists(f_path):
                os.remove(f_path)
        if os.path.exists(out_dir):
            try:
                os.rmdir(out_dir)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["extractimages", "pdfrawimages"],
    cmd_help={
        "help": "Extract all embedded raster images from a PDF file.",
        "example": "extractimages (replying to PDF)",
    },
    requires_reply=True,
)
async def extract_embedded_images(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🖼 Extracting embedded images from PDF...")
    out_dir = f"temp/xtra_pdf/extracted_imgs_{m.id}"
    os.makedirs(out_dir, exist_ok=True)
    extracted = []

    try:

        def _extract():
            doc = fitz.open(pdf_path)
            img_list = []
            count = 0
            for p_idx in range(doc.page_count):
                page_imgs = doc.get_page_images(p_idx)
                for img_info in page_imgs:
                    xref = img_info[0]
                    base_img = doc.extract_image(xref)
                    ext = base_img.get("ext", "png")
                    img_bytes = base_img.get("image")
                    count += 1
                    fn = os.path.join(out_dir, f"img_{count}.{ext}")
                    with open(fn, "wb") as f:
                        f.write(img_bytes)
                    img_list.append(fn)
                    if count >= 10:
                        break
                if count >= 10:
                    break
            doc.close()
            return img_list

        extracted = await asyncio.get_running_loop().run_in_executor(None, _extract)
        if not extracted:
            return await msg.edit_msg("ℹ️ No embedded raster images found in this PDF.")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        for img_fn in extracted:
            await c.send_file(target_chat, img_fn, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to extract images: <code>{e}</code>")
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
        for fn in extracted:
            if os.path.exists(fn):
                os.remove(fn)
        if os.path.exists(out_dir):
            try:
                os.rmdir(out_dir)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["pdftotext", "pdf2txt"],
    cmd_help={
        "help": "Extract all selectable text from a PDF file.",
        "example": "pdftotext (replying to PDF)",
    },
    requires_reply=True,
)
async def pdf_to_text(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("📝 Extracting text from PDF...")
    try:

        def _read_text():
            doc = fitz.open(pdf_path)
            full_text = []
            for p_idx in range(doc.page_count):
                page_text = doc[p_idx].get_text()
                if page_text.strip():
                    full_text.append(f"--- Page {p_idx + 1} ---\n{page_text}")
            doc.close()
            return "\n\n".join(full_text)

        extracted = await asyncio.get_running_loop().run_in_executor(None, _read_text)
        if not extracted.strip():
            return await msg.edit_msg("ℹ️ No selectable text found (document may be a scanned image).")

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        if len(extracted) <= 3000:
            await msg.edit_msg(f"📝 <b>Extracted PDF Text:</b>\n\n<pre>{extracted[:2800]}</pre>")
        else:
            txt_file = f"temp/xtra_pdf/{os.path.splitext(filename)[0]}.txt"
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(extracted)
            await c.send_file(
                target_chat,
                txt_file,
                caption=f"📝 <b>Extracted Text:</b> <code>{filename}</code> ({len(extracted):,} characters)",
                reply_to=m.id,
            )
            await msg.delete_if_self()
            if os.path.exists(txt_file):
                os.remove(txt_file)
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to extract text: <code>{e}</code>")
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)


# ==========================================
# Security & Protection (Encrypt, Decrypt)
# ==========================================


@Friday.register_on_cmd(
    ["pdfprotect", "pdfencrypt"],
    cmd_help={
        "help": "Encrypt a PDF file with AES-256 and protect it with a password.",
        "example": "pdfprotect myPassword123 (replying to PDF)",
    },
    requires_reply=True,
    requires_input=True,
)
async def protect_pdf(c: Client, m: Message):
    password = m.user_input.strip()
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🔒 Encrypting PDF with AES-256...")
    out_pdf = f"temp/xtra_pdf/protected_{os.path.basename(pdf_path)}"

    try:

        def _encrypt():
            doc = fitz.open(pdf_path)
            doc.save(out_pdf, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password, deflate=True)
            doc.close()

        await asyncio.get_running_loop().run_in_executor(None, _encrypt)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        report = (
            f"🔒 <b>PDF Protected Successfully</b>\n\n"
            f"<b>• File:</b> <code>{filename}</code>\n"
            f"<b>• Cipher:</b> <code>AES-256 Bit Encryption</code>\n"
            f"<b>• Password:</b> <code>{password}</code>"
        )
        await c.send_file(target_chat, out_pdf, caption=report, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Encryption failed: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["pdfunlock", "pdfdecrypt"],
    cmd_help={
        "help": "Remove password protection and decrypt an encrypted PDF document.",
        "example": "pdfunlock myPassword123 (replying to PDF)",
    },
    requires_reply=True,
    requires_input=True,
)
async def unlock_pdf(c: Client, m: Message):
    password = m.user_input.strip()
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🔓 Decrypting protected PDF...")
    out_pdf = f"temp/xtra_pdf/unlocked_{os.path.basename(pdf_path)}"

    try:

        def _decrypt():
            doc = fitz.open(pdf_path)
            if doc.is_encrypted:
                auth = doc.authenticate(password)
                if not auth:
                    doc.close()
                    raise PermissionError("Incorrect password. Unable to decrypt document.")
            doc.save(out_pdf, deflate=True)
            doc.close()

        await asyncio.get_running_loop().run_in_executor(None, _decrypt)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        report = f"🔓 <b>PDF Decrypted Successfully</b>\n<b>• File:</b> <code>{filename}</code>\nPassword restrictions permanently removed."
        await c.send_file(target_chat, out_pdf, caption=report, reply_to=m.id)
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Decryption failed: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                os.remove(p)


# ==========================================
# Modification (Rotate, Watermark, Numbers, Grayscale)
# ==========================================


@Friday.register_on_cmd(
    ["pdfrotate", "rotatepdf"],
    cmd_help={
        "help": "Rotate all pages in a PDF document (90, 180, or 270 degrees).",
        "example": "pdfrotate 90 (replying to PDF)",
    },
    requires_reply=True,
)
async def rotate_pdf(c: Client, m: Message):
    raw_angle = (m.user_input or "90").strip()
    try:
        angle = int(raw_angle)
        if angle not in (90, 180, 270):
            angle = 90
    except ValueError:
        angle = 90

    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message(f"🔄 Rotating PDF pages by {angle}°...")
    out_pdf = f"temp/xtra_pdf/rotated_{os.path.basename(pdf_path)}"

    try:

        def _rot():
            doc = fitz.open(pdf_path)
            for page in doc:
                page.set_rotation(page.rotation + angle)
            doc.save(out_pdf, deflate=True)
            doc.close()

        await asyncio.get_running_loop().run_in_executor(None, _rot)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_pdf,
            caption=f"🔄 <b>PDF Rotated by {angle}°</b>\n<b>• File:</b> <code>{filename}</code>",
            reply_to=m.id,
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to rotate PDF: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["pdfwatermark", "watermarkpdf"],
    cmd_help={
        "help": "Add a prominent watermark text box across all pages of a PDF.",
        "example": "pdfwatermark CONFIDENTIAL (replying to PDF)",
    },
    requires_reply=True,
    requires_input=True,
)
async def watermark_pdf(c: Client, m: Message):
    wm_text = m.user_input.strip()
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message(f"🏷 Stamping watermark '<code>{wm_text}</code>'...")
    out_pdf = f"temp/xtra_pdf/watermarked_{os.path.basename(pdf_path)}"

    try:

        def _wm():
            doc = fitz.open(pdf_path)
            for page in doc:
                rect = fitz.Rect(40, page.rect.height / 2 - 40, page.rect.width - 40, page.rect.height / 2 + 40)
                page.insert_textbox(
                    rect,
                    wm_text,
                    fontsize=32,
                    color=(0.75, 0.75, 0.75),
                    align=fitz.TEXT_ALIGN_CENTER,
                )
            doc.save(out_pdf, deflate=True)
            doc.close()

        await asyncio.get_running_loop().run_in_executor(None, _wm)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_pdf,
            caption=f"🏷 <b>Watermarked PDF</b>\n<b>• Stamp:</b> <code>{wm_text}</code>\n<b>• File:</b> <code>{filename}</code>",
            reply_to=m.id,
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to watermark PDF: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["pdfnumbers", "pdfpagenum"],
    cmd_help={
        "help": "Insert sequential page numbers ('Page X of Y') at the footer of each page.",
        "example": "pdfnumbers (replying to PDF)",
    },
    requires_reply=True,
)
async def add_pdf_page_numbers(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🔢 Numbering PDF pages...")
    out_pdf = f"temp/xtra_pdf/numbered_{os.path.basename(pdf_path)}"

    try:

        def _num():
            doc = fitz.open(pdf_path)
            total = doc.page_count
            for idx, page in enumerate(doc):
                label = f"Page {idx + 1} of {total}"
                point = fitz.Point(page.rect.width / 2 - 35, page.rect.height - 25)
                page.insert_text(point, label, fontsize=9, color=(0.4, 0.4, 0.4))
            doc.save(out_pdf, deflate=True)
            doc.close()

        await asyncio.get_running_loop().run_in_executor(None, _num)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_pdf,
            caption=f"🔢 <b>Page Numbers Added</b>\n<b>• File:</b> <code>{filename}</code>",
            reply_to=m.id,
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to number PDF: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                os.remove(p)


@Friday.register_on_cmd(
    ["pdfbw", "pdfgrayscale"],
    cmd_help={
        "help": "Convert a full-color PDF into pure grayscale / black and white.",
        "example": "pdfbw (replying to PDF)",
    },
    requires_reply=True,
)
async def pdf_to_grayscale(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("⚪ Converting PDF to Grayscale...")
    out_pdf = f"temp/xtra_pdf/gray_{os.path.basename(pdf_path)}"

    try:

        def _gray():
            doc_in = fitz.open(pdf_path)
            doc_out = fitz.open()
            for page in doc_in:
                pix = page.get_pixmap(colorspace=fitz.csGRAY, dpi=150)
                p_out = doc_out.new_page(width=page.rect.width, height=page.rect.height)
                p_out.insert_image(page.rect, pixmap=pix)
            doc_out.save(out_pdf, garbage=4, deflate=True)
            doc_in.close()
            doc_out.close()

        await asyncio.get_running_loop().run_in_executor(None, _gray)
        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_pdf,
            caption=f"⚪ <b>Grayscale PDF Converted</b>\n<b>• File:</b> <code>{filename}</code>",
            reply_to=m.id,
        )
        await msg.delete_if_self()
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to convert to grayscale: <code>{e}</code>")
    finally:
        for p in (pdf_path, out_pdf):
            if os.path.exists(p):
                os.remove(p)


# ==========================================
# Inspection & Studio Interactive Panel
# ==========================================


@Friday.register_on_cmd(
    ["pdfinfo", "pdfspecs"],
    cmd_help={
        "help": "Inspect complete metadata, encryption, and dimensions of a PDF file.",
        "example": "pdfinfo (replying to .pdf)",
    },
    requires_reply=True,
)
async def pdf_info(c: Client, m: Message):
    pdf_path, filename = await _download_replied_pdf(m)
    if not pdf_path:
        return await m.handle_message("❌ Please reply to a valid PDF file.")

    msg = await m.handle_message("🔍 Inspecting PDF metadata...")
    try:

        def _inspect():
            doc = fitz.open(pdf_path)
            meta = doc.metadata or {}
            pages = doc.page_count
            is_enc = doc.is_encrypted
            first_p = doc[0] if pages > 0 else None
            dims = f"{int(first_p.rect.width)} × {int(first_p.rect.height)} pt" if first_p else "N/A"
            doc.close()
            return meta, pages, is_enc, dims

        meta, pages, is_enc, dims = await asyncio.get_running_loop().run_in_executor(None, _inspect)
        file_size = Essentials.humanbytes(os.path.getsize(pdf_path))

        report = (
            f"📄 <b>PDF Document Specifications:</b>\n\n"
            f"<b>• File Name:</b> <code>{filename}</code>\n"
            f"<b>• File Size:</b> <code>{file_size}</code>\n"
            f"<b>• Total Pages:</b> <code>{pages}</code>\n"
            f"<b>• Dimensions:</b> <code>{dims}</code>\n"
            f"<b>• Encrypted:</b> <code>{'Yes 🔒' if is_enc else 'No 🔓'}</code>\n"
            f"<b>• Title:</b> <code>{meta.get('title') or 'N/A'}</code>\n"
            f"<b>• Author:</b> <code>{meta.get('author') or 'N/A'}</code>\n"
            f"<b>• Subject:</b> <code>{meta.get('subject') or 'N/A'}</code>\n"
            f"<b>• Creator:</b> <code>{meta.get('creator') or 'N/A'}</code>\n"
            f"<b>• Producer:</b> <code>{meta.get('producer') or 'N/A'}</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Failed to inspect PDF: <code>{e}</code>")
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)


@Friday.register_on_cmd(
    ["pdfstudio", "pdfedit"],
    cmd_help={
        "help": "Open an interactive iLovePDF Studio panel with one-tap buttons for the replied PDF.",
        "example": "pdfstudio (replying to PDF)",
    },
    requires_reply=True,
)
async def pdf_studio(c: Client, m: Message):
    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not rm.file or not (rm.file.name and rm.file.name.lower().endswith(".pdf")):
        return await m.handle_message("❌ Please reply to a valid PDF document to open the iLovePDF Studio.")

    filename = getattr(rm.file, "name", "Document.pdf")
    panel_text = (
        f"📑 <b>Friday iLovePDF Studio</b>\n\n"
        f"<b>Target Document:</b> <code>{filename}</code>\n\n"
        f"<i>Select an action below or use standalone commands:</i>\n"
        f"• <code>.pdfcompress</code> — Shrink file size\n"
        f"• <code>.pdftoimg [page]</code> — Render high-res images\n"
        f"• <code>.pdftotext</code> — Extract all selectable text\n"
        f"• <code>.pdfsplit [1-3]</code> — Extract page range\n"
        f"• <code>.pdfdelete [2,4]</code> — Remove pages\n"
        f"• <code>.pdfrotate [90/180]</code> — Rotate document\n"
        f"• <code>.pdfnumbers</code> — Add Page X of Y footer\n"
        f"• <code>.pdfwatermark [text]</code> — Stamp watermark\n"
        f"• <code>.pdfprotect [pass]</code> — AES-256 encrypt\n"
        f"• <code>.pdfunlock [pass]</code> — Decrypt document\n"
        f"• <code>.pdfbw</code> — Convert to grayscale"
    )

    buttons = [
        [
            Button.inline("🗜 Compress", data=f"pdf_compress_{rm.id}"),
            Button.inline("🖼 To Images", data=f"pdf_toimg_{rm.id}"),
        ],
        [
            Button.inline("📝 Extract Text", data=f"pdf_txt_{rm.id}"),
            Button.inline("🔄 Rotate 90°", data=f"pdf_rot_{rm.id}"),
        ],
        [
            Button.inline("🔢 Page Numbers", data=f"pdf_num_{rm.id}"),
            Button.inline("⚪ Grayscale", data=f"pdf_gray_{rm.id}"),
        ],
        [
            Button.inline("🔍 Document Specs", data=f"pdf_info_{rm.id}"),
            Button.inline("🖼 Raw Images", data=f"pdf_imgs_{rm.id}"),
        ],
    ]

    await m.handle_message(panel_text, buttons=buttons)


@Friday.bot.on_callback_query(pattern=r"^pdf_([a-z]+)_(\d+)$")
async def on_pdf_studio_callback(event):
    data = event.data.decode("utf-8")
    parts = data.split("_")
    action = parts[1]
    msg_id = int(parts[2])

    chat_id = event.chat_id
    c = event.client
    await event.answer("⚡ Processing PDF action...", alert=False)

    try:
        orig_msg = await c.get_messages(chat_id, ids=msg_id)
        if not orig_msg or not orig_msg.file:
            return await event.respond("❌ Target PDF message could not be loaded.")

        os.makedirs("temp/xtra_pdf", exist_ok=True)
        pdf_path = await orig_msg.download_media("temp/xtra_pdf/")
        if not pdf_path or not os.path.exists(pdf_path):
            return await event.respond("❌ Failed to download source PDF.")

        out_pdf = f"temp/xtra_pdf/studio_{action}_{orig_msg.id}.pdf"
        filename = getattr(orig_msg.file, "name", "document.pdf")

        if action == "compress":
            doc = fitz.open(pdf_path)
            orig_sz = os.path.getsize(pdf_path)
            doc.save(out_pdf, garbage=4, deflate=True, clean=True)
            new_sz = os.path.getsize(out_pdf)
            doc.close()
            saved = max(0, orig_sz - new_sz)
            await c.send_file(
                chat_id,
                out_pdf,
                caption=f"🗜 <b>Optimized PDF:</b> <code>{Essentials.humanbytes(new_sz)}</code> (saved {Essentials.humanbytes(saved)})",
                reply_to=msg_id,
            )
        elif action == "rot":
            doc = fitz.open(pdf_path)
            for page in doc:
                page.set_rotation(page.rotation + 90)
            doc.save(out_pdf, deflate=True)
            doc.close()
            await c.send_file(
                chat_id, out_pdf, caption=f"🔄 <b>Rotated 90°:</b> <code>{filename}</code>", reply_to=msg_id
            )
        elif action == "num":
            doc = fitz.open(pdf_path)
            total = doc.page_count
            for idx, page in enumerate(doc):
                label = f"Page {idx + 1} of {total}"
                point = fitz.Point(page.rect.width / 2 - 35, page.rect.height - 25)
                page.insert_text(point, label, fontsize=9, color=(0.4, 0.4, 0.4))
            doc.save(out_pdf, deflate=True)
            doc.close()
            await c.send_file(
                chat_id, out_pdf, caption=f"🔢 <b>Numbered PDF:</b> <code>{filename}</code>", reply_to=msg_id
            )
        elif action == "gray":
            doc_in = fitz.open(pdf_path)
            doc_out = fitz.open()
            for page in doc_in:
                pix = page.get_pixmap(colorspace=fitz.csGRAY, dpi=150)
                p_out = doc_out.new_page(width=page.rect.width, height=page.rect.height)
                p_out.insert_image(page.rect, pixmap=pix)
            doc_out.save(out_pdf, garbage=4, deflate=True)
            doc_in.close()
            doc_out.close()
            await c.send_file(
                chat_id, out_pdf, caption=f"⚪ <b>Grayscale PDF:</b> <code>{filename}</code>", reply_to=msg_id
            )
        elif action == "toimg":
            doc = fitz.open(pdf_path)
            pix = doc[0].get_pixmap(dpi=150)
            img_out = f"temp/xtra_pdf/page_1_{orig_msg.id}.png"
            pix.save(img_out)
            doc.close()
            await c.send_file(chat_id, img_out, caption=f"📄 Page 1 of <code>{filename}</code>", reply_to=msg_id)
            if os.path.exists(img_out):
                os.remove(img_out)
        elif action == "txt":
            doc = fitz.open(pdf_path)
            full_txt = "\n\n".join(p.get_text() for p in doc if p.get_text().strip())
            doc.close()
            if not full_txt.strip():
                await event.respond("ℹ️ No selectable text found in this PDF.")
            elif len(full_txt) <= 2500:
                await event.respond(f"📝 <b>Text Preview:</b>\n\n<pre>{full_txt[:2300]}</pre>")
            else:
                txt_path = f"temp/xtra_pdf/text_{orig_msg.id}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(full_txt)
                await c.send_file(
                    chat_id, txt_path, caption=f"📝 Text extracted from <code>{filename}</code>", reply_to=msg_id
                )
                if os.path.exists(txt_path):
                    os.remove(txt_path)
        elif action == "info":
            doc = fitz.open(pdf_path)
            pages = doc.page_count
            dims = f"{int(doc[0].rect.width)} × {int(doc[0].rect.height)}" if pages > 0 else "N/A"
            doc.close()
            await event.respond(
                f"📄 <b>Document Specs:</b>\n<b>• Pages:</b> <code>{pages}</code>\n<b>• Size:</b> <code>{Essentials.humanbytes(os.path.getsize(pdf_path))}</code>\n<b>• Dims:</b> <code>{dims} pt</code>"
            )
        elif action == "imgs":
            doc = fitz.open(pdf_path)
            count = 0
            for p_idx in range(doc.page_count):
                for img_info in doc.get_page_images(p_idx):
                    base_img = doc.extract_image(img_info[0])
                    ext = base_img.get("ext", "png")
                    img_fn = f"temp/xtra_pdf/extracted_{count + 1}.{ext}"
                    with open(img_fn, "wb") as f:
                        f.write(base_img.get("image"))
                    await c.send_file(chat_id, img_fn, reply_to=msg_id)
                    if os.path.exists(img_fn):
                        os.remove(img_fn)
                    count += 1
                    if count >= 5:
                        break
                if count >= 5:
                    break
            doc.close()
            if count == 0:
                await event.respond("ℹ️ No embedded raster images found.")

        for f in (pdf_path, out_pdf):
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
    except Exception as e:
        await event.respond(f"❌ Studio action failed: <code>{e}</code>")
