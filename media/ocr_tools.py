# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import io
import shutil
import base64
from typing import Optional, Dict, Any, Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import pytesseract
    from PIL import Image
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

# MongoDB collection for dynamic OCR configurations
ocr_db = Friday.db.make_collection("OCR_SETTINGS")

SUPPORTED_LANGUAGES = {
    "eng": "English",
    "spa": "Spanish",
    "fre": "French",
    "ger": "German",
    "rus": "Russian",
    "hin": "Hindi",
    "ara": "Arabic",
    "jpn": "Japanese",
    "kor": "Korean",
    "chi_sim": "Chinese Simplified",
    "por": "Portuguese",
    "ita": "Italian",
    "tur": "Turkish",
}


def _is_tesseract_available() -> bool:
    """Check if local Tesseract OCR binary and Python library are available."""
    if not HAS_PYTESSERACT:
        return False
    # Check if tesseract binary exists in PATH
    if shutil.which("tesseract"):
        return True
    # Common Windows installation path fallback
    win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(win_path):
        pytesseract.pytesseract.tesseract_cmd = win_path
        return True
    return False


async def _get_ocr_config() -> Dict[str, Any]:
    """Retrieve runtime or persisted OCR settings."""
    cfg = await ocr_db.find_one({"_id": "ocr_config"}) or {}
    api_key = cfg.get("api_key") or os.getenv("OCR_SPACE_API_KEY") or os.getenv("OCR_API_KEY") or "helloworld"
    custom_url = cfg.get("custom_url") or os.getenv("OCR_CUSTOM_API_URL")
    custom_key = cfg.get("custom_key") or os.getenv("OCR_CUSTOM_API_KEY")
    prefer_engine = cfg.get("prefer_engine") or os.getenv("OCR_DEFAULT_ENGINE", "auto")
    return {
        "api_key": api_key,
        "custom_url": custom_url,
        "custom_key": custom_key,
        "prefer_engine": prefer_engine,
    }


async def _perform_custom_ai_ocr(file_bytes: bytes, filename: str, endpoint_url: str, api_key: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Query user's self-hosted OCR AI model endpoint (e.g. FastAPI, Surya, PaddleOCR, vLLM/Ollama)."""
    headers = {"User-Agent": "FridayUserbot/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Try multipart form upload first
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            files = {"file": (filename, file_bytes)}
            res = await client.post(endpoint_url, headers=headers, files=files)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    text = data.get("text") or data.get("result") or data.get("parsed_text") or data.get("content")
                    if text:
                        return text.strip(), "Custom AI Endpoint"
                elif isinstance(data, str):
                    return data.strip(), "Custom AI Endpoint"
    except Exception:
        pass

    # Try Base64 JSON payload
    try:
        b64_img = base64.b64encode(file_bytes).decode("utf-8")
        json_payload = {
            "image": b64_img,
            "filename": filename,
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(endpoint_url, headers=headers, json=json_payload)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    text = data.get("text") or data.get("result") or data.get("parsed_text") or data.get("content")
                    if text:
                        return text.strip(), "Custom AI Endpoint"
                elif isinstance(data, str):
                    return data.strip(), "Custom AI Endpoint"
    except Exception as e:
        return None, f"Custom AI error: {e}"

    return None, "Custom AI endpoint returned empty response."


def _perform_local_tesseract(file_path: str, lang: str = "eng") -> Tuple[Optional[str], Optional[str]]:
    """Extract text using locally installed Tesseract OCR engine."""
    try:
        img = Image.open(file_path)
        # Map ocr.space codes to tesseract lang codes
        tess_lang = "eng"
        if lang == "spa":
            tess_lang = "spa"
        elif lang == "fre":
            tess_lang = "fra"
        elif lang == "ger":
            tess_lang = "deu"
        elif lang == "rus":
            tess_lang = "rus"
        elif lang == "hin":
            tess_lang = "hin"
        elif lang == "ara":
            tess_lang = "ara"
        elif lang == "jpn":
            tess_lang = "jpn"
        elif lang == "chi_sim":
            tess_lang = "chi_sim"

        text = pytesseract.image_to_string(img, lang=tess_lang)
        return text.strip(), "Local Tesseract"
    except Exception as e:
        return None, f"Tesseract error: {e}"


async def _perform_ocr_space(file_bytes: bytes, filename: str, api_key: str, lang: str = "eng", is_table: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """Query OCR Space API with user's key or default."""
    url = "https://api.ocr.space/parse/image"
    payload = {
        "apikey": api_key,
        "language": lang,
        "isOverlayRequired": False,
        "isTable": is_table,
        "detectOrientation": True,
        "scale": True,
        "OCREngine": 2,
    }
    files = {"file": (filename, file_bytes)}

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(url, data=payload, files=files)
            if res.status_code == 200:
                data = res.json()
                if data.get("IsErroredOnProcessing"):
                    err = data.get("ErrorMessage", ["OCR Error"])[0]
                    return None, err
                results = data.get("ParsedResults", [])
                if results:
                    text = results[0].get("ParsedText", "").strip()
                    engine_label = "OCR.space (Custom Key)" if api_key != "helloworld" else "OCR.space (Public Free)"
                    return text, engine_label
    except Exception as e:
        return None, str(e)
    return None, "Empty response from OCR.space"


async def _translate_text(text: str, target_lang: str) -> Optional[str]:
    """Helper to translate text via Lingva or MyMemory."""
    try:
        url = f"https://lingva.ml/api/v1/auto/{target_lang}/{text[:1000]}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                return res.json().get("translation")
    except Exception:
        pass
    return None


@Friday.register_on_cmd(
    ["ocr", "readtext", "scanphoto"],
    cmd_help={
        "help": "Extract text from replied image/document supporting OCR Space, Local Tesseract, and Self-Hosted AI OCR endpoints.",
        "example": "ocr (reply to photo)\nocr -l spa (Spanish)\nocr -trans hi (Translate to Hindi)\nocr -tess (Force local Tesseract)\nocr -custom (Force custom AI endpoint)",
    },
)
async def ocr_image(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for OCR.")

    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (rm.photo or rm.sticker or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("image/"))):
        return await m.handle_message("❌ Please reply to an image, screenshot, or document photo.")

    raw = m.user_input.strip() if m.user_input else ""
    lang = "eng"
    target_trans = None
    is_table = False
    clean_lines = False
    force_tess = "-tess" in raw or "-tesseract" in raw
    force_custom = "-custom" in raw or "-ai" in raw
    force_space = "-space" in raw

    if "-l" in raw:
        parts = raw.split("-l")
        raw = parts[0].strip()
        lang_cand = parts[1].strip().split()[0].lower()
        if lang_cand in SUPPORTED_LANGUAGES:
            lang = lang_cand

    if "-trans" in raw:
        parts = raw.split("-trans")
        raw = parts[0].strip()
        target_trans = parts[1].strip().split()[0].lower()

    if "-table" in raw:
        is_table = True

    if "-clean" in raw:
        clean_lines = True

    config = await _get_ocr_config()
    msg = await m.handle_message("👁️‍🗨️ Initializing OCR recognition pipeline...")

    os.makedirs("temp/xtra_ocr", exist_ok=True)
    local_path = await rm.download_media("temp/xtra_ocr/")

    if not local_path or not os.path.exists(local_path):
        return await msg.edit_msg("❌ Failed to download replied media.")

    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()

        extracted_text = None
        engine_used = "Unknown"
        err_detail = None

        # 1. Custom Self-Hosted AI Model Endpoint (if forced or configured)
        if (force_custom or (config.get("custom_url") and config.get("prefer_engine") == "custom")) and config.get("custom_url"):
            extracted_text, engine_used = await _perform_custom_ai_ocr(
                file_bytes, os.path.basename(local_path), config["custom_url"], config.get("custom_key")
            )

        # 2. Local Tesseract (if forced or detected and preferred)
        if not extracted_text and (force_tess or (_is_tesseract_available() and config.get("prefer_engine") == "tesseract")):
            extracted_text, engine_used = _perform_local_tesseract(local_path, lang=lang)

        # 3. Fallback to OCR.Space (user custom key or default helloworld)
        if not extracted_text:
            extracted_text, engine_used = await _perform_ocr_space(
                file_bytes, os.path.basename(local_path), api_key=config["api_key"], lang=lang, is_table=is_table
            )

        # 4. Fallback to Local Tesseract if OCR.space failed and Tesseract is present
        if not extracted_text and _is_tesseract_available():
            extracted_text, engine_used = _perform_local_tesseract(local_path, lang=lang)

        if not extracted_text:
            return await msg.edit_msg(f"❌ OCR failed to extract text.\nDetails: <code>{engine_used}</code>")

        if clean_lines:
            extracted_text = " ".join(extracted_text.split())

        char_count = len(extracted_text)
        line_count = len(extracted_text.splitlines())

        translation_block = ""
        if target_trans:
            trans_result = await _translate_text(extracted_text, target_trans)
            if trans_result:
                translation_block = (
                    f"\n\n🌐 <b>Translation ({target_trans.upper()}):</b>\n"
                    f"<code>{trans_result}</code>"
                )

        header = (
            f"📄 <b>OCR Recognition Report</b>\n"
            f"• <b>Engine:</b> <code>{engine_used}</code>\n"
            f"• <b>Language:</b> <code>{SUPPORTED_LANGUAGES.get(lang, lang)}</code>\n"
            f"• <b>Characters:</b> <code>{char_count}</code> | <b>Lines:</b> <code>{line_count}</code>\n\n"
        )

        if len(extracted_text) < 3000:
            final_report = f"{header}<code>{extracted_text}</code>{translation_block}"
            await msg.edit_msg(final_report)
        else:
            txt_path = os.path.join("temp/xtra_ocr", f"ocr_{m.id}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"--- EXTRACTED OCR TEXT ({engine_used}) ---\n\n{extracted_text}\n\n")
                if translation_block:
                    f.write(f"--- TRANSLATION ---\n\n{translation_block}\n")

            target_chat = m.chat_id or getattr(m.chat, "id", None)
            await c.send_file(
                target_chat,
                txt_path,
                caption=f"{header}<i>(Text was too long for Telegram message, attached as document)</i>",
                reply_to=m.id,
            )
            try:

                await msg.delete()

            except Exception:

                pass
            if os.path.exists(txt_path):
                os.remove(txt_path)
    except Exception as e:
        await msg.edit_msg(f"❌ OCR error: <code>{e}</code>")
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["ocrset", "ocrkey"],
    cmd_help={
        "help": "Set a custom OCR Space API key or restore default.",
        "example": "ocrset K8765432188957 or ocrset default",
    },
    requires_input=True,
)
async def set_ocr_api_key(c: Client, m: Message):
    key = m.user_input.strip()
    if key.lower() in ["default", "reset", "clear"]:
        await ocr_db.update_one({"_id": "ocr_config"}, {"$set": {"api_key": "helloworld"}}, upsert=True)
        return await m.handle_message("✅ <b>OCR API Key reset:</b> Restored default zero-key configuration.")

    await ocr_db.update_one({"_id": "ocr_config"}, {"$set": {"api_key": key}}, upsert=True)
    masked = key[:4] + "*" * (len(key) - 8) + key[-4:] if len(key) > 8 else "***"
    await m.handle_message(f"✅ <b>Custom OCR API Key saved:</b> <code>{masked}</code>")


@Friday.register_on_cmd(
    ["ocrcustom", "ocrai"],
    cmd_help={
        "help": "Set or disable a custom self-hosted AI OCR endpoint (e.g. FastAPI / Surya / PaddleOCR / Ollama).",
        "example": "ocrcustom http://localhost:8000/ocr or ocrcustom off",
    },
    requires_input=True,
)
async def set_custom_ocr(c: Client, m: Message):
    raw = m.user_input.strip()
    if raw.lower() in ["off", "disable", "reset", "none"]:
        await ocr_db.update_one({"_id": "ocr_config"}, {"$unset": {"custom_url": "", "custom_key": ""}}, upsert=True)
        return await m.handle_message("✅ <b>Custom OCR AI Endpoint disabled:</b> Using OCR.space and local Tesseract engines.")

    parts = raw.split()
    url = parts[0]
    key = parts[1] if len(parts) > 1 else None

    await ocr_db.update_one(
        {"_id": "ocr_config"},
        {"$set": {"custom_url": url, "custom_key": key, "prefer_engine": "custom"}},
        upsert=True,
    )
    await m.handle_message(
        "🚀 <b>Custom OCR AI Endpoint Configured!</b>\n\n"
        f"• <b>URL:</b> <code>{url}</code>\n"
        f"• <b>Auth Header:</b> <code>{'Bearer ***' if key else 'None (Open endpoint)'}</code>\n"
        "• <b>Priority:</b> Preferred over cloud API.\n\n"
        "<i>Friday will now forward scanned documents to your self-hosted AI model!</i>"
    )


@Friday.register_on_cmd(
    ["ocrconfig", "ocrstatus"],
    cmd_help={
        "help": "Inspect current OCR engine status, custom API keys, and Tesseract availability.",
        "example": "ocrconfig",
    },
)
async def ocr_status(c: Client, m: Message):
    cfg = await _get_ocr_config()
    tess_avail = "✅ Available & Ready" if _is_tesseract_available() else "⚠️ Not installed (Cloud fallback active)"
    
    key = cfg.get("api_key", "helloworld")
    key_status = "Default (helloworld)" if key == "helloworld" else f"Custom ({key[:4]}***{key[-4:] if len(key)>8 else ''})"

    custom_url = cfg.get("custom_url") or "None (Disabled)"
    prefer = cfg.get("prefer_engine", "auto").capitalize()

    report = (
        "⚙️ <b>Friday OCR Engine Architecture</b>\n\n"
        f"• <b>Primary Cloud API:</b> <code>OCR.space</code>\n"
        f"  - <b>API Key:</b> <code>{key_status}</code>\n"
        f"• <b>Local Engine:</b> <code>{tess_avail}</code>\n"
        f"• <b>Self-Hosted AI Endpoint:</b> <code>{custom_url}</code>\n"
        f"• <b>Active Preference:</b> <code>{prefer}</code>\n\n"
        "<b>Management Commands:</b>\n"
        "• <code>.ocrset &lt;api_key&gt;</code> - Set custom OCR.space key\n"
        "• <code>.ocrcustom &lt;url&gt; [token]</code> - Set custom self-hosted AI endpoint\n"
        "• <code>.ocr -tess</code> - Force local Tesseract on replied image\n"
        "• <code>.ocr -custom</code> - Force custom AI endpoint on replied image"
    )
    await m.handle_message(report)
