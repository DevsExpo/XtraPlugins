# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import base64
import contextlib
import html
import hashlib
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from telethon import custom

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors, iuser_check
from Main.utils.custom_filters import filters

logger = logging.getLogger("friday.ai_imagine")

_COLLECTION = "AI_IMAGINE"
_CACHE_DIR = Path("cache/imagine")

# Dimension Presets
_DEFAULT_W, _DEFAULT_H = 1024, 1024
_HD_W, _HD_H = 1024, 1024
_WIDE_W, _WIDE_H = 1792, 1024
_TALL_W, _TALL_H = 1024, 1792

# Default Pollinations API
_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

# Default Local In-Device Endpoints (Automatic1111 / Forge / SD.Next / ComfyUI / LocalAI)
_DEFAULT_LOCAL_SD_URL = "http://127.0.0.1:7860"
_DEFAULT_LOCAL_COMFY_URL = "http://127.0.0.1:8188"

# Popular Model Aliases for Pollinations
_POLLINATIONS_MODELS = {
    "flux": "flux",
    "flux-realism": "flux-realism",
    "realism": "flux-realism",
    "flux-anime": "flux-anime",
    "anime": "flux-anime",
    "flux-3d": "flux-3d",
    "3d": "flux-3d",
    "flux-cablyai": "flux-cablyai",
    "turbo": "turbo",
    "any-dark": "any-dark",
    "dark": "any-dark",
    "midjourney": "midjourney",
}

_PROVIDER_DISPLAY = {
    "pollinations": "☁️ Pollinations (Free Cloud)",
    "local": "🏠 In-Device (Local Stable Diffusion)",
    "device": "🏠 In-Device (Local Stable Diffusion)",
    "sd": "🏠 In-Device (Local Stable Diffusion)",
    "comfyui": "🏠 In-Device (Local ComfyUI)",
    "openai": "✨ OpenAI DALL-E",
    "custom": "🌐 Custom Image API",
}


def _col():
    """Retrieve the AI_IMAGINE collection from Friday database."""
    if Friday.db is not None:
        return Friday.db.make_collection(_COLLECTION)
    return None


async def _get_img_cfg(chat_id: Union[int, str]) -> Dict[str, Any]:
    """Fetch image generation settings for user/chat with fallback to global default."""
    col = _col()
    doc = None
    if col is not None:
        doc = await col.find_one({"_id": f"imgcfg_{chat_id}"})
        if not doc:
            doc = await col.find_one({"_id": "imgcfg_global"})

    provider = doc.get("provider") if doc else None
    if not provider:
        provider = "pollinations"

    model = doc.get("model") if doc else None
    if not model:
        model = "flux" if provider == "pollinations" else "dall-e-3" if provider == "openai" else "default"

    local_url = doc.get("local_url") if doc else None
    if not local_url:
        local_url = await Friday.config.get_env("LOCAL_SD_URL") or _DEFAULT_LOCAL_SD_URL

    custom_url = doc.get("custom_url") if doc else None
    if not custom_url:
        custom_url = await Friday.config.get_env("IMAGE_API_URL")

    custom_key = doc.get("custom_key") if doc else None
    if not custom_key:
        custom_key = await Friday.config.get_env("IMAGE_API_KEY") or await Friday.config.get_env("OPENAI_API_KEY")

    return {
        "provider": provider.lower(),
        "model": model,
        "local_url": local_url.rstrip("/"),
        "custom_url": custom_url.rstrip("/") if custom_url else None,
        "custom_key": custom_key,
    }


async def _set_img_cfg(chat_id: Union[int, str], **kwargs: Any) -> None:
    """Save image configuration for chat and global fallback."""
    col = _col()
    if col is None:
        return
    await col.find_one_and_update(
        {"_id": f"imgcfg_{chat_id}"},
        {"$set": kwargs},
        upsert=True,
    )
    await col.find_one_and_update(
        {"_id": "imgcfg_global"},
        {"$set": kwargs},
        upsert=True,
    )


def _prompt_seed(prompt: str) -> int:
    """Deterministic seed from prompt hash."""
    return int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)


def _build_pollinations_url(
    prompt: str,
    width: int = _DEFAULT_W,
    height: int = _DEFAULT_H,
    negative: Optional[str] = None,
    seed: Optional[int] = None,
    model: str = "flux",
    nologo: bool = True,
) -> str:
    resolved_model = _POLLINATIONS_MODELS.get(model.lower(), model)
    encoded = urllib.parse.quote(prompt)
    url = f"{_POLLINATIONS_BASE}/{encoded}"
    params = {
        "width": str(width),
        "height": str(height),
        "model": resolved_model,
        "nologo": "true" if nologo else "false",
    }
    if negative:
        params["negative_prompt"] = negative
    if seed is not None:
        params["seed"] = str(seed)
    return url + "?" + urllib.parse.urlencode(params)


async def _generate_pollinations(
    prompt: str,
    width: int,
    height: int,
    negative: Optional[str],
    model: str,
    seed: Optional[int] = None,
) -> Tuple[Optional[Path], Optional[str]]:
    """Download image from Pollinations. Returns (local_path, url)."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fname = _CACHE_DIR / f"pol_{_prompt_seed(f'{prompt}_{model}_{seed}')}.jpg"

    url = _build_pollinations_url(prompt, width, height, negative, seed=seed, model=model)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "FridayUserbot/2.0"})
        if resp.status_code == 200:
            fname.write_bytes(resp.content)
            return fname, url
        logger.warning(f"Pollinations returned status {resp.status_code}")
    except Exception as exc:
        logger.error(f"Pollinations generation failed: {exc}")
    return None, url


# ─── 2. In-Device / Local AI Generator (SD WebUI / Forge / SD.Next) ───────────


async def _check_local_sd_status(base_url: str) -> Tuple[bool, List[str]]:
    """Check if in-device Stable Diffusion server is reachable and fetch available models."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url}/sdapi/v1/sd-models")
            if resp.status_code == 200:
                models = [m.get("model_name", m.get("title", "")) for m in resp.json()]
                return True, models
    except Exception:
        pass
    return False, []


async def _generate_local_sd(
    prompt: str,
    width: int,
    height: int,
    negative: Optional[str],
    model: Optional[str],
    base_url: str,
    steps: int = 20,
) -> Tuple[Optional[Path], Optional[str]]:
    """Generate image on local in-device Stable Diffusion WebUI instance."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fname = _CACHE_DIR / f"loc_{_prompt_seed(prompt)}.png"

    payload: Dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative or "",
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": 7.0,
    }
    if model and model not in ("default", "none", "auto"):
        payload["override_settings"] = {"sd_model_checkpoint": model}

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{base_url}/sdapi/v1/txt2img", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            images = data.get("images", [])
            if images:
                img_bytes = base64.b64decode(images[0])
                fname.write_bytes(img_bytes)
                return fname, None
        return None, f"Local SD returned status {resp.status_code}"
    except httpx.ConnectError:
        return None, f"Could not connect to in-device server at {base_url}. Is Stable Diffusion running?"
    except Exception as exc:
        return None, f"In-device generation error: {exc}"


# ─── 3. OpenAI / Custom Cloud API Generator ───────────────────────────────────


async def _generate_openai_compatible(
    prompt: str,
    width: int,
    height: int,
    model: str,
    api_url: Optional[str],
    api_key: Optional[str],
) -> Tuple[Optional[Path], Optional[str]]:
    """Generate image via OpenAI (DALL-E) or custom OpenAI-compatible endpoint."""
    if not api_key:
        return None, "No API key found. Set OPENAI_API_KEY or IMAGE_API_KEY via config."

    endpoint = api_url or "https://api.openai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "model": model or "dall-e-3",
        "n": 1,
        "size": f"{width}x{height}",
    }

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fname = _CACHE_DIR / f"cust_{_prompt_seed(prompt)}.png"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            item = (data.get("data") or [{}])[0]
            if "b64_json" in item:
                fname.write_bytes(base64.b64decode(item["b64_json"]))
                return fname, None
            if "url" in item:
                img_url = item["url"]
                async with httpx.AsyncClient(timeout=60.0) as dl_client:
                    img_resp = await dl_client.get(img_url)
                if img_resp.status_code == 200:
                    fname.write_bytes(img_resp.content)
                    return fname, img_url
        return None, f"API error: {resp.status_code} - {resp.text[:200]}"
    except Exception as exc:
        return None, f"Custom API generation error: {exc}"


def _parse_imagine_args(raw: str) -> Dict[str, Any]:
    """
    Parse .imagine arguments with support for custom models, dimensions, and flags.
    Flags supported:
      --model / -m <model_name>
      --provider / -p <provider_name>
      --neg <negative_prompt>
      --size <w>x<h>
      --steps <n>
      --seed <n>
    """
    result: Dict[str, Any] = {
        "prompt": "",
        "negative": "",
        "width": _DEFAULT_W,
        "height": _DEFAULT_H,
        "model": None,
        "provider": None,
        "steps": 20,
        "seed": None,
    }

    # Extract flags using regex
    # 1. Negative prompt
    neg_match = re.search(r"(?:--neg|-neg)\s+(.+?)(?=\s+(?:--|-)[a-zA-Z]|$)", raw, re.IGNORECASE)
    if neg_match:
        result["negative"] = neg_match.group(1).strip()
        raw = raw[: neg_match.start()] + raw[neg_match.end() :]

    # 2. Custom Model flag: --model <name> or -m <name>
    model_match = re.search(r"(?:--model|-m)\s+([^\s]+)", raw, re.IGNORECASE)
    if model_match:
        result["model"] = model_match.group(1).strip()
        raw = raw[: model_match.start()] + raw[model_match.end() :]

    # 3. Provider flag: --provider <name> or -p <name>
    provider_match = re.search(r"(?:--provider|-p)\s+([^\s]+)", raw, re.IGNORECASE)
    if provider_match:
        result["provider"] = provider_match.group(1).strip().lower()
        raw = raw[: provider_match.start()] + raw[provider_match.end() :]

    # 4. Custom Size flag: --size <w>x<h>
    size_match = re.search(r"(?:--size|-s)\s+(\d+)x(\d+)", raw, re.IGNORECASE)
    if size_match:
        result["width"] = int(size_match.group(1))
        result["height"] = int(size_match.group(2))
        raw = raw[: size_match.start()] + raw[size_match.end() :]

    # 5. Steps flag: --steps <n>
    steps_match = re.search(r"(?:--steps)\s+(\d+)", raw, re.IGNORECASE)
    if steps_match:
        result["steps"] = int(steps_match.group(1))
        raw = raw[: steps_match.start()] + raw[steps_match.end() :]

    # 6. Seed flag: --seed <n>
    seed_match = re.search(r"(?:--seed)\s+(\d+)", raw, re.IGNORECASE)
    if seed_match:
        result["seed"] = int(seed_match.group(1))
        raw = raw[: seed_match.start()] + raw[seed_match.end() :]

    parts = raw.strip().split(None, 1)
    if not parts:
        return result

    mode = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if mode == "hd":
        result["width"], result["height"] = _HD_W, _HD_H
        result["prompt"] = rest
    elif mode == "wide":
        result["width"], result["height"] = _WIDE_W, _WIDE_H
        result["prompt"] = rest
    elif mode == "tall":
        result["width"], result["height"] = _TALL_W, _TALL_H
        result["prompt"] = rest
    else:
        result["prompt"] = raw.strip()

    return result


@Friday.register_on_cmd(
    ["imagine", "img", "gen"],
    cmd_help={
        "help": (
            "Generate AI images from text prompts.\n"
            "Supports cloud AI models (Pollinations, OpenAI) and in-device local AI (Stable Diffusion WebUI / Forge / ComfyUI).\n"
            "Options: hd · wide · tall · --neg <avoid> · --model <model> · --provider <pollinations|local|openai|custom>"
        ),
        "example": [
            "imagine a futuristic cyberpunk city at night",
            "imagine hd a majestic dragon over mountains --neg blur, dark",
            "imagine wide a neon samurai --model flux-realism",
            "imagine a mystical enchanted forest --provider local",
            "imagine a golden astronaut on mars --model dall-e-3 --provider openai",
        ],
    },
    requires_input=True,
)
@log_errors
async def ai_imagine_cmd(c: Client, m: Message):
    raw = (m.user_input or "").strip()
    parsed = _parse_imagine_args(raw)
    prompt = parsed["prompt"]
    negative = parsed["negative"]
    width = parsed["width"]
    height = parsed["height"]

    if not prompt:
        return await m.handle_message(
            "🎨 <b>Usage:</b> <code>.imagine &lt;prompt&gt; [flags]</code>\n\n"
            "<b>Flags:</b>\n"
            "• <code>--model &lt;name&gt;</code> (e.g. <code>flux-realism</code>, <code>turbo</code>, <code>dall-e-3</code>)\n"
            "• <code>--provider &lt;name&gt;</code> (<code>pollinations</code>, <code>local</code>, <code>openai</code>)\n"
            "• <code>--neg &lt;text&gt;</code> (negative prompt)\n"
            "• <code>--size &lt;w&gt;x&lt;h&gt;</code> (e.g. <code>1024x1024</code>, <code>1792x1024</code>)\n\n"
            "<i>Example:</i> <code>.imagine a majestic lion in cosmic space --model flux-realism</code>"
        )

    chat_id = m.chat_id or m.sender_id
    cfg = await _get_img_cfg(chat_id)

    # Active provider and model resolution
    provider = (parsed["provider"] or cfg["provider"]).lower()
    model = parsed["model"] or cfg["model"]
    provider_label = _PROVIDER_DISPLAY.get(provider, f"🌐 {provider.title()}")

    status = await m.handle_message(
        f"🎨 <i>Generating image via {provider_label}…</i>\n"
        f"<b>Model:</b> <code>{html.escape(str(model))}</code>\n"
        f"<b>Prompt:</b> <code>{html.escape(prompt[:120])}</code>"
    )

    local_path: Optional[Path] = None
    err_or_url: Optional[str] = None

    # ── Execute Generation ──
    if provider in ("local", "device", "sd"):
        base_url = cfg["local_url"]
        local_path, err_or_url = await _generate_local_sd(
            prompt=prompt,
            width=width,
            height=height,
            negative=negative,
            model=model,
            base_url=base_url,
            steps=parsed["steps"],
        )
    elif provider in ("openai", "custom"):
        local_path, err_or_url = await _generate_openai_compatible(
            prompt=prompt,
            width=width,
            height=height,
            model=model,
            api_url=cfg["custom_url"],
            api_key=cfg["custom_key"],
        )
    else:
        # Default: Pollinations cloud
        local_path, err_or_url = await _generate_pollinations(
            prompt=prompt,
            width=width,
            height=height,
            negative=negative,
            model=model or "flux",
            seed=parsed["seed"],
        )

    # Caption preparation
    result_caption = (
        f"🎨 <b>Generated Image</b>\n"
        f"<b>Provider:</b> {provider_label}\n"
        f"<b>Model:</b> <code>{html.escape(str(model))}</code>\n"
        f"<b>Prompt:</b> <i>{html.escape(prompt[:250])}</i>"
    )
    if negative:
        result_caption += f"\n<b>Negative:</b> <i>{html.escape(negative[:100])}</i>"
    result_caption += f"\n<b>Resolution:</b> {width}×{height}"

    if status and hasattr(status, "delete"):
        with contextlib.suppress(Exception):
            await status.delete()

    if local_path and local_path.exists():
        await c.send_file(
            m.chat_id,
            file=str(local_path),
            caption=result_caption,
            parse_mode="html",
            reply_to=m.id,
        )
    else:
        err_msg = err_or_url or "Unknown generation failure."
        if provider in ("local", "device", "sd"):
            err_msg += (
                f"\n\n💡 <i>To run in-device, ensure your Stable Diffusion WebUI / Forge is running at</i> "
                f"<code>{cfg['local_url']}</code> <i>with</i> <code>--api</code> <i>enabled.</i>\n"
                f"<i>Or switch back to cloud with:</i> <code>.setimgprovider pollinations</code>"
            )
        await m.handle_message(f"❌ <b>Image Generation Failed:</b>\n{err_msg}")


@Friday.register_on_cmd(
    ["setimgmodel", "aimgmodel"],
    cmd_help={
        "help": "Set default AI model for image generation (Pollinations, Local SD, or OpenAI).",
        "example": [
            "setimgmodel flux",
            "setimgmodel flux-realism",
            "setimgmodel turbo",
            "setimgmodel dall-e-3",
        ],
    },
    requires_input=True,
)
@log_errors
async def set_img_model_cmd(c: Client, m: Message):
    arg = (m.user_input or "").strip()
    chat_id = m.chat_id or m.sender_id
    await _set_img_cfg(chat_id, model=arg)
    await m.handle_message(
        f"🎨 <b>Default Image Model updated!</b>\n• <b>Active Model:</b> <code>{html.escape(arg)}</code>"
    )


@Friday.register_on_cmd(
    ["setimgprovider", "aimgprovider"],
    cmd_help={
        "help": "Switch image generation provider: pollinations (cloud), local (in-device SD), openai, or custom.",
        "example": [
            "setimgprovider pollinations",
            "setimgprovider local",
            "setimgprovider openai",
        ],
    },
    requires_input=True,
)
@log_errors
async def set_img_provider_cmd(c: Client, m: Message):
    arg = (m.user_input or "").strip().lower()
    valid = ("pollinations", "local", "device", "sd", "openai", "custom")
    if arg not in valid:
        return await m.handle_message(
            f"❌ <b>Invalid provider:</b> <code>{arg}</code>\n"
            f"<b>Supported:</b> <code>pollinations</code>, <code>local</code>, <code>openai</code>, <code>custom</code>"
        )

    # Normalize aliases
    norm_provider = "local" if arg in ("device", "sd") else arg
    chat_id = m.chat_id or m.sender_id
    await _set_img_cfg(chat_id, provider=norm_provider)
    label = _PROVIDER_DISPLAY.get(norm_provider, norm_provider.title())
    await m.handle_message(f"🎨 <b>Image Provider switched!</b>\n• <b>Active Provider:</b> {label}")


@Friday.register_on_cmd(
    ["imginfo", "aimginfo"],
    cmd_help={
        "help": "Check active image generation settings, available models, and in-device server status.",
        "example": ["imginfo"],
    },
)
@log_errors
async def img_info_cmd(c: Client, m: Message):
    chat_id = m.chat_id or m.sender_id
    cfg = await _get_img_cfg(chat_id)
    provider = cfg["provider"]
    provider_label = _PROVIDER_DISPLAY.get(provider, provider.title())

    # Check local in-device server connectivity
    local_online, local_models = await _check_local_sd_status(cfg["local_url"])
    local_status = f"🟢 Online ({len(local_models)} models found)" if local_online else "🔴 Offline (Not reachable)"

    lines = [
        "🎨 <b>AI Image Generation Configuration</b>\n",
        f"• <b>Current Provider:</b> {provider_label}",
        f"• <b>Current Model:</b> <code>{cfg['model']}</code>",
        f"• <b>In-Device Server URL:</b> <code>{cfg['local_url']}</code>",
        f"• <b>In-Device Status:</b> {local_status}",
        "\n<b>Available Cloud Models (Pollinations):</b>",
        "<code>flux</code> · <code>flux-realism</code> · <code>flux-anime</code> · <code>flux-3d</code> · <code>turbo</code> · <code>any-dark</code> · <code>midjourney</code>",
        "\n<b>Usage Tips:</b>",
        "• <code>.imagine &lt;prompt&gt; --model flux-realism</code>",
        "• <code>.imagine &lt;prompt&gt; --provider local</code> (in-device)",
        "• <code>.setimgprovider &lt;pollinations|local|openai&gt;</code>",
        "• <code>.setimgmodel &lt;model&gt;</code>",
    ]
    await m.handle_message("\n".join(lines))


@Friday.bot.on_inline_query(filters.regex(r"^imagine\s+(.+)", flags=2))
@log_errors
@iuser_check
async def imagine_inline_handler(c, iq):
    match = re.match(r"^imagine\s+(.+)", iq.text, re.IGNORECASE)
    if not match:
        return

    parsed = _parse_imagine_args(match.group(1))
    prompt = parsed["prompt"]
    model = parsed["model"] or "flux"
    url = _build_pollinations_url(prompt, _DEFAULT_W, _DEFAULT_H, model=model)

    builder = iq.builder
    try:
        result = builder.photo(
            file=url,
            text=f"🎨 <b>{html.escape(prompt[:100])}</b>\n<i>Model: {html.escape(model)} · Pollinations</i>",
            parse_mode="html",
            buttons=[
                [
                    custom.Button.inline("🔁 Regenerate", f"img_regen#{prompt[:64]}".encode()),
                    custom.Button.inline("📏 HD", f"img_hd#{prompt[:60]}".encode()),
                    custom.Button.inline("🖼 Wide", f"img_wide#{prompt[:60]}".encode()),
                ],
            ],
        )
        await iq.answer([result], cache_time=60)
    except Exception as exc:
        logger.error(f"imagine inline error: {exc}")
        result = builder.article(
            title=f"🎨 {prompt[:50]}",
            description="Click to view generated image",
            text=f"🎨 <b>{html.escape(prompt[:200])}</b>\n\n<a href='{url}'>View Image</a>",
            parse_mode="html",
        )
        await iq.answer([result], cache_time=30)


@Friday.bot.on_callback_query(filters.regex(r"^img_(regen|hd|wide)#(.+)"))
@log_errors
@iuser_check
async def imagine_variant_callback(c, cq):
    data = cq.data.decode() if isinstance(cq.data, bytes) else str(cq.data)
    match = re.match(r"^img_(regen|hd|wide)#(.+)", data)
    if not match:
        return await cq.answer("❌ Invalid request.", alert=True)

    mode, prompt = match.group(1), match.group(2)
    await cq.answer(f"⏳ Generating {mode} version…")

    if mode == "hd":
        w, h = _HD_W, _HD_H
    elif mode == "wide":
        w, h = _WIDE_W, _WIDE_H
    else:
        w, h = _DEFAULT_W, _DEFAULT_H

    import random

    seed = random.randint(1, 999999) if mode == "regen" else None
    local_path, url = await _generate_pollinations(prompt, w, h, None, "flux", seed=seed)

    buttons = [
        [
            custom.Button.inline("🔁 Regenerate", f"img_regen#{prompt[:64]}".encode()),
            custom.Button.inline("📏 HD", f"img_hd#{prompt[:60]}".encode()),
            custom.Button.inline("🖼 Wide", f"img_wide#{prompt[:60]}".encode()),
        ],
    ]

    caption = f"🎨 <b>Generated Image [{mode.upper()}]</b>\n<i>{html.escape(prompt[:200])}</i>\nResolution: {w}×{h}"

    if local_path and local_path.exists():
        await cq.edit(caption, file=str(local_path), parse_mode="html", buttons=buttons)
    else:
        await cq.edit(
            f"❌ Generation failed. <a href='{url}'>Try directly</a>",
            parse_mode="html",
        )
