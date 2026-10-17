# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import time
from typing import List, Dict, Any
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


def _get_todo_col():
    """Access the persistent Friday database collection for todos."""
    return Friday.db.make_collection("TODOS")


@Friday.register_on_cmd(
    ["todo", "tasks"],
    cmd_help={
        "help": "Track your daily tasks with checkboxes and status marking in the Friday database.",
        "example": "todo (views list) | todo add Buy coffee | todo done 1 | todo del 1 | todo clear",
    },
)
async def todo_manager(c: Client, m: Message):
    col = _get_todo_col()
    user_id = m.sender_id or (getattr(c, "me", None) and c.me.id) or 0
    raw = (m.user_input or "").strip()

    if not raw or raw.lower() == "list":
        try:
            from Main.utils.inline_helper import send_inline_widget
            if await send_inline_widget(c, m, "todo"):
                return
        except Exception:
            pass

        cursor = col.find({"user_id": user_id})
        todos = await cursor.to_list(length=None) if hasattr(cursor, "to_list") else [doc async for doc in cursor]

        if not todos:
            return await m.handle_message(
                "📝 <b>Todo List is currently empty!</b>\n"
                "Add tasks using <code>.todo add &lt;task text&gt;</code>"
            )

        active = [t for t in todos if not t.get("done")]
        completed = [t for t in todos if t.get("done")]

        lines = ["📋 <b>Your Task List</b>\n"]
        if active:
            lines.append("<b>Active Tasks:</b>")
            for t in active:
                prio = " 🔴" if t.get("high_prio") else ""
                lines.append(f"<code>[{t.get('task_id', t.get('id', 1))}]</code> ⬜ {t['text']}{prio}")

        if completed:
            lines.append("\n<b>Completed:</b>")
            for t in completed:
                lines.append(f"<code>[{t.get('task_id', t.get('id', 1))}]</code> <s>✅ {t['text']}</s>")

        lines.append(f"\n<i>Summary: {len(active)} pending, {len(completed)} completed</i>")
        return await m.handle_message("\n".join(lines))

    parts = raw.split(" ", 1)
    action = parts[0].lower()
    content = parts[1].strip() if len(parts) > 1 else ""

    if action in ("add", "+", "new"):
        if not content:
            return await m.handle_message("❌ Please provide task description: <code>.todo add Buy groceries</code>")

        is_high = "!high" in content.lower()
        clean_text = content.replace("!high", "").replace("!HIGH", "").strip()

        cursor = col.find({"user_id": user_id})
        existing = await cursor.to_list(length=None) if hasattr(cursor, "to_list") else [doc async for doc in cursor]
        next_id = (max([t.get("task_id", 0) for t in existing], default=0) + 1) if existing else 1

        new_doc = {
            "user_id": user_id,
            "task_id": next_id,
            "text": clean_text,
            "done": False,
            "high_prio": is_high,
            "created_at": int(time.time()),
        }
        await col.insert_one(new_doc)
        prio_tag = " [High Priority]" if is_high else ""
        return await m.handle_message(f"✅ Added task <code>#{next_id}</code>: <b>{clean_text}</b>{prio_tag}")

    elif action in ("done", "check", "complete"):
        if not content.isdigit():
            return await m.handle_message("❌ Specify task ID: <code>.todo done 1</code>")

        target_id = int(content)
        res = await col.update_one(
            {"user_id": user_id, "task_id": target_id},
            {"$set": {"done": True, "completed_at": int(time.time())}},
        )

        if getattr(res, "matched_count", 0) == 0:
            return await m.handle_message(f"❌ Task <code>#{target_id}</code> not found.")

        return await m.handle_message(f"🎉 Marked task <code>#{target_id}</code> as <b>Completed!</b>")

    elif action in ("undone", "uncheck"):
        if not content.isdigit():
            return await m.handle_message("❌ Specify task ID: <code>.todo undone 1</code>")

        target_id = int(content)
        res = await col.update_one(
            {"user_id": user_id, "task_id": target_id},
            {"$set": {"done": False}},
        )

        if getattr(res, "matched_count", 0) == 0:
            return await m.handle_message(f"❌ Task <code>#{target_id}</code> not found.")

        return await m.handle_message(f"🔄 Task <code>#{target_id}</code> marked back as <b>Pending</b>.")

    elif action in ("del", "delete", "rm", "remove"):
        if not content.isdigit():
            return await m.handle_message("❌ Specify task ID: <code>.todo del 1</code>")

        target_id = int(content)
        res = await col.delete_one({"user_id": user_id, "task_id": target_id})

        if getattr(res, "deleted_count", 0) == 0:
            return await m.handle_message(f"❌ Task <code>#{target_id}</code> not found.")

        return await m.handle_message(f"🗑 Deleted task <code>#{target_id}</code>.")

    elif action in ("clear", "clean"):
        if content.lower() == "all":
            await col.delete_many({"user_id": user_id})
            return await m.handle_message("🗑 <b>All tasks have been cleared from database.</b>")
        else:
            res = await col.delete_many({"user_id": user_id, "done": True})
            count = getattr(res, "deleted_count", 0)
            return await m.handle_message(f"🧹 <b>Cleared {count} completed task(s).</b> (Use <code>.todo clear all</code> to wipe active tasks too)")

    else:
        return await m.handle_message(
            "<b>Usage:</b>\n"
            "• <code>.todo</code> - view list\n"
            "• <code>.todo add &lt;text&gt;</code> - add task\n"
            "• <code>.todo done &lt;id&gt;</code> - mark as done\n"
            "• <code>.todo undone &lt;id&gt;</code> - unmark\n"
            "• <code>.todo del &lt;id&gt;</code> - delete task\n"
            "• <code>.todo clear</code> - clear completed"
        )


# ==========================================
# Interactive Inline Checklist Handlers
# ==========================================

if getattr(Friday, "bot", None):
    from telethon import custom
    from Main.utils.custom_filters import filters
    from Main.utils.inline_helper import is_authorized_cb

    async def _render_todo_checklist(user_id: int):
        col = _get_todo_col()
        cursor = col.find({"user_id": user_id})
        todos = await cursor.to_list(length=None) if hasattr(cursor, "to_list") else [doc async for doc in cursor]

        if not todos:
            text = (
                "📝 <b>Your Todo Checklist is Empty!</b>\n\n"
                "Add tasks using: <code>.todo add &lt;task description&gt;</code>"
            )
            buttons = [
                [custom.Button.inline("🔄 Refresh", f"todo_ref_{user_id}".encode("utf-8"))]
            ]
            return text, buttons

        active = [t for t in todos if not t.get("done")]
        completed = [t for t in todos if t.get("done")]

        text = (
            f"📋 <b>Interactive Task Checklist</b>\n\n"
            f"• <b>Pending:</b> <code>{len(active)}</code> | <b>Completed:</b> <code>{len(completed)}</code>\n"
            f"<i>Tap any task button below to toggle done / undone:</i>\n"
        )

        btn_rows = []
        display_todos = (active + completed)[:6]
        for t in display_todos:
            tid = t.get("task_id", 1)
            is_done = t.get("done", False)
            icon = "✅" if is_done else "⬜"
            prio = " 🔴" if t.get("high_prio") and not is_done else ""
            label = f"{icon} #{tid} {t['text'][:22]}{prio}"
            btn_rows.append([
                custom.Button.inline(label, f"todo_tgl_{user_id}_{tid}".encode("utf-8"))
            ])

        control_row = [
            custom.Button.inline("🧹 Clear Done", f"todo_clr_{user_id}".encode("utf-8")),
            custom.Button.inline("🔄 Refresh", f"todo_ref_{user_id}".encode("utf-8")),
        ]
        btn_rows.append(control_row)
        return text, btn_rows

    @Friday.bot.on_inline_query(filters.regex(r"^todo$"))
    async def todo_inline_query_handler(c, iq):
        builder = iq.builder
        user_id = iq.sender_id or 0
        text, buttons = await _render_todo_checklist(user_id)
        res = builder.article(
            title="📝 Interactive Todo Checklist",
            description="View and check off your tasks with inline buttons.",
            text=text,
            buttons=buttons,
            parse_mode="html",
        )
        await iq.answer([res])

    @Friday.bot.on_callback_query(filters.regex(r"^todo_"))
    async def todo_callback_handler(c, cq):
        data = cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data)
        parts = data.split("_")
        action = parts[1]
        owner_user_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        if not is_authorized_cb(cq, allowed_user_id=owner_user_id):
            return await cq.answer("⛔ Access denied: This is a private task list.", alert=True)

        col = _get_todo_col()

        if action == "tgl":
            target_tid = int(parts[3])
            doc = await col.find_one({"user_id": owner_user_id, "task_id": target_tid})
            if doc:
                new_done = not doc.get("done", False)
                await col.update_one(
                    {"user_id": owner_user_id, "task_id": target_tid},
                    {"$set": {"done": new_done}}
                )
                state_str = "Completed! 🎉" if new_done else "Pending"
                await cq.answer(f"Task #{target_tid} marked as {state_str}")
        elif action == "clr":
            res = await col.delete_many({"user_id": owner_user_id, "done": True})
            cnt = getattr(res, "deleted_count", 0)
            await cq.answer(f"Cleared {cnt} completed tasks!", alert=True)
        elif action == "ref":
            await cq.answer("Checklist refreshed!")

        text, buttons = await _render_todo_checklist(owner_user_id)
        try:
            await cq.edit(text, buttons=buttons, parse_mode="html")
        except Exception:
            pass

