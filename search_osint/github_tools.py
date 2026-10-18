# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _clean_repo_slug(raw: str) -> str:
    s = raw.strip()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    return s


@Friday.register_on_cmd(
    ["git", "github", "repo"],
    cmd_help={
        "help": "Inspect a GitHub repository's stars, forks, issues, license, and metadata.",
        "example": "git Friday/Friday or git https://github.com/torvalds/linux",
    },
    requires_input=True,
)
async def github_repo_inspect(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    slug = _clean_repo_slug(m.user_input)
    if "/" not in slug:
        return await m.handle_message("❌ Please provide <code>owner/repo</code>: e.g. <code>.git Friday/Friday</code>")

    msg = await m.handle_message(f"🐙 Inspecting repository <b>{slug}</b>...")
    api_url = f"https://api.github.com/repos/{slug}"
    headers = {"User-Agent": "FridayUserbot/1.0", "Accept": "application/vnd.github.v3+json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(api_url, headers=headers)

        if res.status_code == 404:
            return await msg.edit_msg(f"❌ Repository <code>{slug}</code> not found or is private.")
        if res.status_code != 200:
            return await msg.edit_msg(f"❌ GitHub API returned HTTP {res.status_code}.")

        data = res.json()
        full_name = data.get("full_name", slug)
        desc = data.get("description", "No description provided.")
        stars = data.get("stargazers_count", 0)
        forks = data.get("forks_count", 0)
        issues = data.get("open_issues_count", 0)
        lang = data.get("language", "Unknown")
        license_name = data.get("license", {}).get("spdx_id", "None") if data.get("license") else "None"
        created = data.get("created_at", "")[:10]
        updated = data.get("updated_at", "")[:10]
        html_url = data.get("html_url", f"https://github.com/{slug}")

        report = (
            f"🐙 <b><a href='{html_url}'>{full_name}</a></b>\n"
            f"<i>{desc}</i>\n\n"
            f"<b>• Stars:</b> ⭐ <code>{stars:,}</code>\n"
            f"<b>• Forks:</b> 🍴 <code>{forks:,}</code>\n"
            f"<b>• Open Issues:</b> ⚠️ <code>{issues:,}</code>\n"
            f"<b>• Primary Language:</b> <code>{lang}</code>\n"
            f"<b>• License:</b> <code>{license_name}</code>\n"
            f"<b>• Created:</b> <code>{created}</code>\n"
            f"<b>• Last Push:</b> <code>{updated}</code>\n\n"
            f"🔗 <a href='{html_url}'>View on GitHub</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ GitHub inspection error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["ghuser", "gituser"],
    cmd_help={
        "help": "Lookup a GitHub user's profile, bio, followers, and public repos count.",
        "example": "ghuser torvalds",
    },
    requires_input=True,
)
async def github_user_inspect(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    username = m.user_input.strip().lstrip("@")
    msg = await m.handle_message(f"🐙 Fetching GitHub user <b>{username}</b>...")

    api_url = f"https://api.github.com/users/{username}"
    headers = {"User-Agent": "FridayUserbot/1.0", "Accept": "application/vnd.github.v3+json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(api_url, headers=headers)

        if res.status_code == 404:
            return await msg.edit_msg(f"❌ User <code>{username}</code> not found on GitHub.")
        if res.status_code != 200:
            return await msg.edit_msg(f"❌ GitHub API error: HTTP {res.status_code}")

        data = res.json()
        name = data.get("name") or username
        bio = data.get("bio", "No bio.")
        repos = data.get("public_repos", 0)
        followers = data.get("followers", 0)
        following = data.get("following", 0)
        company = data.get("company", "None")
        location = data.get("location", "None")
        html_url = data.get("html_url", f"https://github.com/{username}")

        report = (
            f"👤 <b><a href='{html_url}'>{name}</a></b> (<code>@{username}</code>)\n"
            f"<i>{bio}</i>\n\n"
            f"<b>• Public Repos:</b> <code>{repos}</code>\n"
            f"<b>• Followers:</b> <code>{followers:,}</code> | <b>Following:</b> <code>{following:,}</code>\n"
            f"<b>• Company:</b> <code>{company}</code>\n"
            f"<b>• Location:</b> <code>{location}</code>\n\n"
            f"🔗 <a href='{html_url}'>GitHub Profile</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ GitHub lookup error: <code>{e}</code>")
