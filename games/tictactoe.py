# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.


from __future__ import annotations

import contextlib
import random
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from telethon import custom
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from Main.utils.custom_filters import filters

_COLLECTION = "GAMES"
_STATS_COLLECTION = "GAME_STATS"

_WINNING_COMBOS = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),  # Rows
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),  # Cols
    (0, 4, 8),
    (2, 4, 6),  # Diagonals
]


def _games_col():
    return Friday.db.make_collection(_COLLECTION)


def _stats_col():
    return Friday.db.make_collection(_STATS_COLLECTION)


def _check_winner_board(board: List[Optional[str]]) -> Optional[str]:
    for a, b, c in _WINNING_COMBOS:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(cell is not None for cell in board):
        return "DRAW"
    return None


def _minimax(board: List[Optional[str]], depth: int, is_maximizing: bool) -> int:
    winner = _check_winner_board(board)
    if winner == "O":  # AI
        return 10 - depth
    elif winner == "X":  # Human
        return depth - 10
    elif winner == "DRAW":
        return 0

    if is_maximizing:
        best_score = -100
        for i in range(9):
            if board[i] is None:
                board[i] = "O"
                score = _minimax(board, depth + 1, False)
                board[i] = None
                best_score = max(best_score, score)
        return best_score
    else:
        best_score = 100
        for i in range(9):
            if board[i] is None:
                board[i] = "X"
                score = _minimax(board, depth + 1, True)
                board[i] = None
                best_score = min(best_score, score)
        return best_score


def _find_best_move(board: List[Optional[str]], difficulty: str = "hard") -> int:
    empty_indices = [i for i, v in enumerate(board) if v is None]
    if not empty_indices:
        return -1

    if difficulty == "easy" and random.random() < 0.65:
        return random.choice(empty_indices)

    best_score = -1000
    best_move = empty_indices[0]
    for i in empty_indices:
        board[i] = "O"
        score = _minimax(board, 0, False)
        board[i] = None
        if score > best_score:
            best_score = score
            best_move = i
    return best_move


def _render_board_buttons(game: Dict[str, Any], finished: bool = False) -> List[List[Any]]:
    board = game["board"]
    game_id = game["game_id"]

    symbols = {
        "X": "❌",
        "O": "⭕",
        None: "⬜",
    }

    buttons = []
    for row in range(3):
        row_buttons = []
        for col in range(3):
            idx = row * 3 + col
            val = board[idx]
            label = symbols[val]
            if finished or val is not None:
                row_buttons.append(custom.Button.inline(label, b"ttt_noop"))
            else:
                row_buttons.append(custom.Button.inline(label, f"ttt_move#{game_id}#{idx}".encode()))
        buttons.append(row_buttons)

    control_row = []
    if not finished:
        control_row.append(custom.Button.inline("🏳️ Resign", f"ttt_resign#{game_id}".encode()))
    else:
        mode = game.get("mode", "ai")
        diff = game.get("difficulty", "hard")
        new_tag = f"{mode}_{diff}"
        control_row.append(custom.Button.inline("🔄 Play Again", f"ttt_new#{new_tag}".encode()))

    buttons.append(control_row)
    return buttons


def _build_status_text(game: Dict[str, Any], winner: Optional[str] = None) -> str:
    p1_name = game["p1_name"]
    p2_name = game["p2_name"]
    mode = game["mode"]
    diff = game.get("difficulty", "hard").title()

    if winner == "DRAW":
        status_line = "🤝 <b>It's a Draw! Well played both!</b>"
    elif winner == "X":
        status_line = f"🎉 <b>{p1_name} (❌) Wins!</b>"
    elif winner == "O":
        status_line = f"🎉 <b>{p2_name} (⭕) Wins!</b>"
    else:
        current_turn = "❌ " + p1_name if game["turn"] == game["p1_id"] else "⭕ " + p2_name
        status_line = f"⏳ <b>Current Turn:</b> {current_turn}"

    mode_label = f"🤖 vs AI ({diff})" if mode == "ai" else "👥 PvP Match"

    return (
        f"🎮 <b>Tic-Tac-Toe Arena</b> <i>[{mode_label}]</i>\n\n"
        f"• <b>Player 1 (❌):</b> {p1_name}\n"
        f"• <b>Player 2 (⭕):</b> {p2_name}\n\n"
        f"{status_line}"
    )


async def _record_stat(user_id: int, result: str) -> None:
    """Record win/loss/draw in stats collection."""
    col = _stats_col()
    field = f"ttt_{result}"
    with contextlib.suppress(Exception):
        await col.find_one_and_update(
            {"_id": str(user_id)},
            {"$inc": {field: 1, "ttt_total": 1}},
            upsert=True,
        )


@Friday.register_on_cmd(
    ["ttt", "tictactoe"],
    cmd_help={
        "help": "Play Tic-Tac-Toe solo vs AI or challenge a friend in group chat.",
        "example": [
            "ttt",
            "ttt easy",
            "ttt @username",
            "ttt stats",
        ],
    },
)
@log_errors
async def ttt_cmd(c: Client, m: Message):
    arg = (m.user_input or "").strip().lower()

    if arg == "stats":
        user_id = m.sender_id
        col = _stats_col()
        doc = await col.find_one({"_id": str(user_id)}) or {}
        wins = doc.get("ttt_wins", 0)
        losses = doc.get("ttt_losses", 0)
        draws = doc.get("ttt_draws", 0)
        total = doc.get("ttt_total", 0)
        win_rate = round((wins / total) * 100, 1) if total else 0.0

        return await m.handle_message(
            f"📊 <b>Tic-Tac-Toe Stats for You</b>\n\n"
            f"• <b>Total Games:</b> <code>{total}</code>\n"
            f"• <b>Wins:</b> 🟢 <code>{wins}</code>\n"
            f"• <b>Losses:</b> 🔴 <code>{losses}</code>\n"
            f"• <b>Draws:</b> 🟡 <code>{draws}</code>\n"
            f"• <b>Win Rate:</b> <code>{win_rate}%</code>"
        )

    game_id = uuid.uuid4().hex[:10]
    p1_id = m.sender_id
    p1_name = getattr(getattr(m, "from_user", None), "first_name", None) or "Player 1"

    # Check for PvP challenge
    mode = "ai"
    difficulty = "hard"
    p2_id = None
    p2_name = "Friday AI"

    if arg == "easy":
        difficulty = "easy"
    elif arg.startswith("@") or m.reply_to_message:
        target = None
        if m.reply_to_message:
            target = m.reply_to_message.sender
        elif arg.startswith("@"):
            with contextlib.suppress(Exception):
                target = await c.get_entity(arg)

        if target and getattr(target, "id", None) != p1_id:
            mode = "pvp"
            p2_id = target.id
            p2_name = getattr(target, "first_name", "Challenger")
        elif target and getattr(target, "id", None) == p1_id:
            return await m.handle_message("😅 <i>You cannot challenge yourself to a match!</i>")

    game_data = {
        "_id": f"ttt_{game_id}",
        "game_id": game_id,
        "chat_id": m.chat_id or p1_id,
        "board": [None] * 9,
        "p1_id": p1_id,
        "p1_name": p1_name,
        "p2_id": p2_id,
        "p2_name": p2_name,
        "mode": mode,
        "difficulty": difficulty,
        "turn": p1_id,
        "status": "active",
        "created_at": time.time(),
    }

    col = _games_col()
    await col.insert_one(game_data)

    text = _build_status_text(game_data)
    buttons = _render_board_buttons(game_data)

    # 1. Try inline query via assistant bot
    sent = False
    if getattr(Friday, "bot_info", None) and getattr(Friday.bot_info, "username", None):
        try:
            results = await c.get_inline_bot_results(Friday.bot_info.username, f"ttt {game_id}")
            if results:
                await results[0].click(m.chat_id)
                sent = True
                with contextlib.suppress(Exception):
                    await m.delete_if_self()
        except Exception:
            pass

    # 2. Fallback: Direct send via bot
    if not sent and getattr(Friday, "_raw_bot", None):
        try:
            await Friday._raw_bot.send_message(m.chat_id, text, buttons=buttons, parse_mode="html")
            sent = True
            with contextlib.suppress(Exception):
                await m.delete_if_self()
        except Exception:
            pass
    if not sent:
        await m.handle_message(text, buttons=buttons)


if getattr(Friday, "bot", None):

    @Friday.bot.on_inline_query(filters.regex(r"^ttt\s+([a-zA-Z0-9_-]+)"))
    @log_errors
    async def ttt_inline_handler(c, iq):
        match = re.search(r"^ttt\s+([a-zA-Z0-9_-]+)", iq.text or "")
        if not match:
            return
        game_id = match.group(1)
        col = _games_col()
        game = await col.find_one({"_id": f"ttt_{game_id}"})
        if not game:
            return
        text = _build_status_text(game)
        buttons = _render_board_buttons(game)
        builder = iq.builder
        result = builder.article(
            title=f"Tic-Tac-Toe: {game['p1_name']} vs {game['p2_name']}",
            text=text,
            parse_mode="html",
            buttons=buttons,
        )
        await iq.answer([result], cache_time=0)


@Friday.bot.on_callback_query(pattern=r"^ttt_")
async def ttt_callback(c, cq):
    data = cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data)

    if data == "ttt_noop":
        return await cq.answer("⚠️ That square is already taken!", alert=False)

    col = _games_col()

    if data.startswith("ttt_new#"):
        params = data.split("#", 1)[1]
        mode, diff = params.split("_", 1) if "_" in params else ("ai", "hard")
        new_gid = uuid.uuid4().hex[:10]
        clicker_id = cq.sender_id
        clicker_name = getattr(cq.sender, "first_name", "Player 1")

        game_data = {
            "_id": f"ttt_{new_gid}",
            "game_id": new_gid,
            "board": [None] * 9,
            "p1_id": clicker_id,
            "p1_name": clicker_name,
            "p2_id": None,
            "p2_name": "Friday AI",
            "mode": mode,
            "difficulty": diff,
            "turn": clicker_id,
            "status": "active",
            "created_at": time.time(),
        }
        await col.insert_one(game_data)
        text = _build_status_text(game_data)
        buttons = _render_board_buttons(game_data)
        with contextlib.suppress(Exception):
            await cq.edit(text, buttons=buttons, parse_mode="html")
        return await cq.answer("🎮 New game started!")

    if data.startswith("ttt_resign#"):
        game_id = data.split("#", 1)[1]
        game = await col.find_one({"_id": f"ttt_{game_id}"})
        if not game or game.get("status") != "active":
            return await cq.answer("Game already ended or not found.", alert=True)

        clicker_id = cq.sender_id
        if clicker_id not in (game["p1_id"], game.get("p2_id")):
            return await cq.answer("⛔ You are not a player in this game!", alert=True)

        # Forfeit
        resigner = game["p1_name"] if clicker_id == game["p1_id"] else game["p2_name"]
        winner = "O" if clicker_id == game["p1_id"] else "X"
        winner_name = game["p2_name"] if clicker_id == game["p1_id"] else game["p1_name"]

        game["status"] = "forfeit"
        await col.find_one_and_update({"_id": f"ttt_{game_id}"}, {"$set": {"status": "forfeit", "winner": winner}})

        if game["mode"] == "ai":
            await _record_stat(game["p1_id"], "losses")
        elif game["mode"] == "pvp":
            winner_id = game["p2_id"] if clicker_id == game["p1_id"] else game["p1_id"]
            await _record_stat(clicker_id, "losses")
            if winner_id:
                await _record_stat(winner_id, "wins")

        text = f"🏳️ <b>{resigner} has resigned!</b>\n\n🎉 <b>{winner_name} wins by forfeit!</b>"
        buttons = _render_board_buttons(game, finished=True)
        with contextlib.suppress(Exception):
            await cq.edit(text, buttons=buttons, parse_mode="html")
        return await cq.answer("🏳️ Forfeited.")

    if data.startswith("ttt_move#"):
        _, game_id, cell_str = data.split("#", 2)
        cell = int(cell_str)

        game = await col.find_one({"_id": f"ttt_{game_id}"})
        if not game or game.get("status") != "active":
            return await cq.answer("Game is already finished!", alert=True)

        board: List[Optional[str]] = game["board"]
        clicker_id = cq.sender_id

        # Turn & Player Validation
        if clicker_id not in (game["p1_id"], game.get("p2_id")):
            return await cq.answer("⛔ You are not a player in this game!", alert=True)

        if clicker_id != game["turn"]:
            return await cq.answer("⏳ Not your turn! Please wait.", alert=True)

        if board[cell] is not None:
            return await cq.answer("Square already occupied!", alert=True)

        # Apply Move
        mark = "X" if clicker_id == game["p1_id"] else "O"
        board[cell] = mark

        # Check for immediate win/draw
        outcome = _check_winner_board(board)

        if outcome:
            game["status"] = "finished"
            game["winner"] = outcome
            await col.find_one_and_update(
                {"_id": f"ttt_{game_id}"}, {"$set": {"board": board, "status": "finished", "winner": outcome}}
            )

            # Record stats
            if outcome == "DRAW":
                await _record_stat(game["p1_id"], "draws")
                if game["p2_id"]:
                    await _record_stat(game["p2_id"], "draws")
            elif outcome == "X":
                await _record_stat(game["p1_id"], "wins")
                if game["p2_id"]:
                    await _record_stat(game["p2_id"], "losses")
            elif outcome == "O":
                if game["p2_id"]:
                    await _record_stat(game["p2_id"], "wins")
                await _record_stat(game["p1_id"], "losses")

            text = _build_status_text(game, winner=outcome)
            buttons = _render_board_buttons(game, finished=True)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer("Game finished!")
        if game["mode"] == "ai":
            ai_move = _find_best_move(board, game.get("difficulty", "hard"))
            if ai_move != -1:
                board[ai_move] = "O"

            ai_outcome = _check_winner_board(board)
            if ai_outcome:
                game["status"] = "finished"
                game["winner"] = ai_outcome
                await col.find_one_and_update(
                    {"_id": f"ttt_{game_id}"}, {"$set": {"board": board, "status": "finished", "winner": ai_outcome}}
                )
                if ai_outcome == "O":
                    await _record_stat(game["p1_id"], "losses")
                elif ai_outcome == "DRAW":
                    await _record_stat(game["p1_id"], "draws")

                text = _build_status_text(game, winner=ai_outcome)
                buttons = _render_board_buttons(game, finished=True)
                with contextlib.suppress(Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")
                return await cq.answer("AI moved!")
            game["turn"] = game["p1_id"]
            await col.find_one_and_update({"_id": f"ttt_{game_id}"}, {"$set": {"board": board, "turn": game["p1_id"]}})
        else:
            next_turn = game["p2_id"] if clicker_id == game["p1_id"] else game["p1_id"]
            game["turn"] = next_turn
            await col.find_one_and_update({"_id": f"ttt_{game_id}"}, {"$set": {"board": board, "turn": next_turn}})

        text = _build_status_text(game)
        buttons = _render_board_buttons(game)
        with contextlib.suppress(Exception):
            await cq.edit(text, buttons=buttons, parse_mode="html")
        await cq.answer()
