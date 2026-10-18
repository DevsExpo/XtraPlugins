# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import base64
import hashlib
import secrets
import string
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@Friday.register_on_cmd(
    ["passgen", "genpass"],
    cmd_help={
        "help": "Generate a cryptographically secure random password.",
        "example": "passgen [length] (default: 16)",
    },
)
async def generate_password(c: Client, m: Message):
    length = 16
    if m.user_input and m.user_input.strip().isdigit():
        length = max(8, min(64, int(m.user_input.strip())))

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    password = "".join(secrets.choice(alphabet) for _ in range(length))

    report = (
        "🔐 <b>Secure Password Generated:</b>\n\n"
        f"<code>{password}</code>\n\n"
        f"<b>• Length:</b> <code>{length}</code> characters\n"
        f"<i>Tip: Tap the password above to copy it to clipboard.</i>"
    )
    await m.handle_message(report)


@Friday.register_on_cmd(
    ["hash"],
    cmd_help={
        "help": "Compute cryptographic checksums (MD5, SHA1, SHA256, SHA512) for text.",
        "example": "hash mysecrettext",
    },
    requires_input=True,
)
async def compute_hashes(c: Client, m: Message):
    text = m.user_input.strip().encode("utf-8")
    md5_hash = hashlib.md5(text).hexdigest()
    sha1_hash = hashlib.sha1(text).hexdigest()
    sha256_hash = hashlib.sha256(text).hexdigest()
    sha512_hash = hashlib.sha512(text).hexdigest()

    report = (
        "🔒 <b>Cryptographic Checksums:</b>\n\n"
        f"<b>• MD5:</b>\n<code>{md5_hash}</code>\n\n"
        f"<b>• SHA-1:</b>\n<code>{sha1_hash}</code>\n\n"
        f"<b>• SHA-256:</b>\n<code>{sha256_hash}</code>\n\n"
        f"<b>• SHA-512:</b>\n<code>{sha512_hash[:64]}...</code>"
    )
    await m.handle_message(report)


@Friday.register_on_cmd(
    ["b64e", "b64d"],
    cmd_help={
        "help": "Encode or decode Base64 strings.",
        "example": "b64e Hello World or b64d SGVsbG8gV29ybGQ=",
    },
    requires_input=True,
)
async def base64_tools(c: Client, m: Message):
    cmd = m.cmd
    text = m.user_input.strip()

    try:
        if cmd == "b64e":
            encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
            report = f"🔐 <b>Base64 Encoded:</b>\n<code>{encoded}</code>"
        else:
            decoded = base64.b64decode(text.encode("utf-8")).decode("utf-8", errors="replace")
            report = f"🔓 <b>Base64 Decoded:</b>\n<code>{decoded}</code>"
        await m.handle_message(report)
    except Exception as e:
        await m.handle_message(f"❌ Base64 error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["fakeuser", "fakeid"],
    cmd_help={
        "help": "Generate a realistic random identity profile for testing.",
        "example": "fakeuser",
    },
)
async def fake_user(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    msg = await m.handle_message("👤 Generating identity profile...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get("https://randomuser.me/api/")

        if res.status_code != 200:
            return await msg.edit_msg("❌ Failed to contact identity service.")

        data = res.json()["results"][0]
        name = f"{data['name']['title']} {data['name']['first']} {data['name']['last']}"
        email = data["email"]
        phone = data["phone"]
        cell = data["cell"]
        loc = f"{data['location']['street']['number']} {data['location']['street']['name']}, {data['location']['city']}, {data['location']['country']}"
        nat = data.get("nat", "US")
        dob = data["dob"]["date"][:10]
        age = data["dob"]["age"]
        user = data["login"]["username"]

        report = (
            "👤 <b>Generated Random Identity:</b>\n\n"
            f"<b>• Name:</b> <code>{name}</code> ({age} y/o, {nat})\n"
            f"<b>• Username:</b> <code>{user}</code>\n"
            f"<b>• Email:</b> <code>{email}</code>\n"
            f"<b>• Phone:</b> <code>{phone}</code> | <code>{cell}</code>\n"
            f"<b>• Address:</b> <code>{loc}</code>\n"
            f"<b>• DOB:</b> <code>{dob}</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Error generating identity: <code>{e}</code>")
