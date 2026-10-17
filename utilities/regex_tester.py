# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import re
import html
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


@Friday.register_on_cmd(
    ["regex", "regexp", "regextest"],
    cmd_help={
        "help": "Test and debug Regular Expressions with match spans and captured group breakdowns.",
        "example": "regex \\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b test@example.com\nregex (\\d{4})-(\\d{2})-(\\d{2}) 2026-10-17",
    },
)
async def regex_test_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message()) if hasattr(m, "get_reply_message") else None
    raw = (m.user_input or "").strip()

    pattern_str = ""
    target_str = ""

    if reply and (reply.text or reply.raw_text):
        pattern_str = raw
        target_str = reply.text or reply.raw_text
    elif raw:
        parts = raw.split(None, 1)
        if len(parts) >= 2:
            pattern_str = parts[0]
            target_str = parts[1]
        else:
            return await m.handle_message("⚠️ <b>Usage:</b> <code>.regex &lt;pattern&gt; &lt;text_to_match&gt;</code> or reply to text.")
    else:
        return await m.handle_message("⚠️ <b>Usage:</b> <code>.regex &lt;pattern&gt; &lt;text_to_match&gt;</code> or reply to text.")

    try:
        regex = re.compile(pattern_str)
    except re.error as err:
        return await m.handle_message(f"❌ <b>Invalid Regex Syntax:</b>\n<code>{html.escape(str(err))}</code>")

    matches = list(regex.finditer(target_str))
    if not matches:
        return await m.handle_message(
            f"🔍 <b>Regex Test Result:</b> ⚪ <i>No match found</i>\n"
            f"• <b>Pattern:</b> <code>{html.escape(pattern_str)}</code>\n"
            f"• <b>Target Length:</b> <code>{len(target_str)} chars</code>"
        )

    lines = []
    for i, match in enumerate(matches[:10], 1):
        span = match.span()
        matched_text = match.group(0)
        groups = match.groups()
        group_info = ""
        if groups:
            group_details = ", ".join(f"G{idx}: <code>{html.escape(str(g))}</code>" for idx, g in enumerate(groups, 1))
            group_info = f"\n   └ Groups: {group_details}"

        lines.append(
            f"<b>Match {i}:</b> [span {span[0]}:{span[1]}] <code>{html.escape(matched_text)}</code>{group_info}"
        )

    overflow = f"\n<i>... and {len(matches) - 10} more matches</i>" if len(matches) > 10 else ""

    report = (
        f"🎯 <b>Regex Evaluation:</b> 🟢 <b>{len(matches)} match(es)</b>\n"
        f"• <b>Pattern:</b> <code>{html.escape(pattern_str)}</code>\n\n"
        + "\n".join(lines)
        + overflow
    )
    await m.handle_message(report)
