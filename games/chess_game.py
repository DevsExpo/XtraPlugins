# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

# Insipired by @chessy_bot (Thanks to https://github.com/Piterden)

from __future__ import annotations

import contextlib
import logging
import random
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import chess
from telethon import custom

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from Main.utils.custom_filters import filters

logger = logging.getLogger("friday.chess")

_COLLECTION = "GAMES"
_STATS_COLLECTION = "GAME_STATS"

# Standard Unicode chess piece glyphs
_PIECES = {
    chess.WHITE: {
        chess.PAWN: "♙",
        chess.KNIGHT: "♘",
        chess.BISHOP: "♗",
        chess.ROOK: "♖",
        chess.QUEEN: "♕",
        chess.KING: "♔",
    },
    chess.BLACK: {
        chess.PAWN: "♟",
        chess.KNIGHT: "♞",
        chess.BISHOP: "♝",
        chess.ROOK: "♜",
        chess.QUEEN: "♛",
        chess.KING: "♚",
    },
}

_PIECE_NAMES = {
    chess.PAWN: "Pawn",
    chess.KNIGHT: "Knight",
    chess.BISHOP: "Bishop",
    chess.ROOK: "Rook",
    chess.QUEEN: "Queen",
    chess.KING: "King",
}

# Heuristic piece values for built-in AI evaluation
_PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

# In-memory selection cache for sub-millisecond response on button clicks
_GAME_SELECTION: Dict[str, Optional[str]] = {}
# In-memory promotion prompt cache: game_id -> (from_sq, to_sq)
_GAME_PROMOTIONS: Dict[str, Optional[Tuple[str, str]]] = {}


def _games_col():
    return Friday.db.make_collection(_COLLECTION)


def _stats_col():
    return Friday.db.make_collection(_STATS_COLLECTION)


def _get_piece_glyph(piece: Optional[chess.Piece]) -> str:
    if not piece:
        return " "
    return _PIECES.get(piece.color, {}).get(piece.piece_type, " ")


def _get_captures_and_material(board: chess.Board) -> Tuple[List[str], List[str], int]:
    """Calculate captured pieces and current material difference from White's perspective."""
    initial_white = {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
    initial_black = {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}

    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p and p.piece_type != chess.KING:
            if p.color == chess.WHITE:
                initial_white[p.piece_type] = initial_white.get(p.piece_type, 0) - 1
            else:
                initial_black[p.piece_type] = initial_black.get(p.piece_type, 0) - 1

    piece_order = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
    b_symbols = {chess.QUEEN: "♛", chess.ROOK: "♜", chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"}
    w_symbols = {chess.QUEEN: "♕", chess.ROOK: "♖", chess.BISHOP: "♗", chess.KNIGHT: "♘", chess.PAWN: "♙"}

    w_captures = []
    for pt in piece_order:
        taken_black = initial_black.get(pt, 0)
        if taken_black > 0:
            w_captures.extend([b_symbols[pt]] * taken_black)

    b_captures = []
    for pt in piece_order:
        taken_white = initial_white.get(pt, 0)
        if taken_white > 0:
            b_captures.extend([w_symbols[pt]] * taken_white)

    score = 0
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p and p.piece_type != chess.KING:
            val = _PIECE_VALUES.get(p.piece_type, 0) // 100
            score += val if p.color == chess.WHITE else -val

    return w_captures, b_captures, score


def _evaluate_board(board: chess.Board) -> int:
    """Evaluate material advantage from White's perspective."""
    if board.is_checkmate():
        return -99999 if board.turn == chess.WHITE else 99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            val = _PIECE_VALUES.get(piece.piece_type, 0)
            score += val if piece.color == chess.WHITE else -val
    return score


def _get_ai_move(board: chess.Board) -> Optional[chess.Move]:
    """Find a smart move using minimax lookahead with randomization."""
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return None

    best_move = legal_moves[0]
    is_white = board.turn == chess.WHITE
    best_score = -999999 if is_white else 999999

    random.shuffle(legal_moves)

    for move in legal_moves:
        board.push(move)
        score = _evaluate_board(board)
        board.pop()

        if is_white and score > best_score:
            best_score = score
            best_move = move
        elif not is_white and score < best_score:
            best_score = score
            best_move = move

    return best_move


def _build_status_text(game: Dict[str, Any], selected_sq: Optional[str] = None) -> str:
    fen = game["fen"]
    board = chess.Board(fen)

    w_name = game.get("w_name", "White")
    b_name = game.get("b_name", "Black")
    is_white_turn = board.turn == chess.WHITE
    status = game.get("status", "active")

    mode_label = "🤖 vs AI Engine" if game["mode"] == "ai" else "👥 PvP Match"
    w_captures, b_captures, mat_diff = _get_captures_and_material(board)

    captures_line = []
    if w_captures or mat_diff > 0:
        lead = f" (+{mat_diff})" if mat_diff > 0 else ""
        captures_line.append(f"⚪ <b>{w_name}:</b> {' '.join(w_captures)}{lead}")
    if b_captures or mat_diff < 0:
        lead = f" (+{-mat_diff})" if mat_diff < 0 else ""
        captures_line.append(f"⚫ <b>{b_name}:</b> {' '.join(b_captures)}{lead}")

    captures_block = ""
    if captures_line:
        captures_block = "\n" + "\n".join(captures_line) + "\n"

    if status == "waiting":
        state_line = "⏳ <b>Waiting for an opponent to join the game...</b>"
    elif board.is_checkmate():
        winner = b_name if is_white_turn else w_name
        winner_side = "Black ⚫" if is_white_turn else "White ⚪"
        state_line = f"🏆 <b>CHECKMATE! {winner} ({winner_side}) Wins!</b>"
    elif board.is_stalemate():
        state_line = "🤝 <b>Stalemate! Game drawn.</b>"
    elif board.is_insufficient_material():
        state_line = "🤝 <b>Draw by Insufficient Material!</b>"
    elif board.can_claim_fifty_moves():
        state_line = "🤝 <b>Draw by 50-move rule!</b>"
    elif board.can_claim_threefold_repetition():
        state_line = "🤝 <b>Draw by Threefold Repetition!</b>"
    elif status == "forfeit":
        state_line = "🏳️ <b>Match ended by Resignation!</b>"
    elif board.is_check():
        active = w_name if is_white_turn else b_name
        turn_label = "⚪ White's" if is_white_turn else "⚫ Black's"
        state_line = f"⚠️ <b>CHECK!</b> {turn_label} turn: <b>{active}</b>"
    else:
        active = w_name if is_white_turn else b_name
        turn_label = "⚪ White's" if is_white_turn else "⚫ Black's"
        state_line = f"⏳ {turn_label} turn: <b>{active}</b>"

    last_move = game.get("last_move")
    last_move_block = f"\n\n<b>Recent Move:</b>\n{last_move}" if last_move else ""

    selection_line = ""
    if selected_sq:
        with contextlib.suppress(Exception):
            p = board.piece_at(chess.parse_square(selected_sq))
            p_sym = _get_piece_glyph(p)
            p_name = _PIECE_NAMES.get(p.piece_type, "Piece") if p else ""
            selection_line = f"\n🎯 Selected: <b>{p_sym} {p_name} ({selected_sq})</b> — <i>tap destination square</i>"

    return (
        f"♟️ <b>Chess Arena</b> <i>[{mode_label}]</i>\n"
        f"• <b>White (⚪):</b> {w_name}\n"
        f"• <b>Black (⚫):</b> {b_name}\n"
        f"{captures_block}\n"
        f"{state_line}"
        f"{last_move_block}"
        f"{selection_line}"
    )


def _render_chess_keyboard(
    game: Dict[str, Any],
    selected_sq: Optional[str] = None,
    promotion_move: Optional[Tuple[str, str]] = None,
) -> List[List[Any]]:
    game_id = game["game_id"]
    fen = game["fen"]
    board = chess.Board(fen)
    status = game.get("status", "active")
    is_game_over = board.is_game_over() or status in ("finished", "forfeit")

    # If match is finished, display Play Again buttons
    if is_game_over:
        return [
            [
                custom.Button.inline("🔄 Play vs AI", "c_new_ai".encode()),
                custom.Button.inline("👥 Play PvP", "c_new_pvp".encode()),
            ]
        ]

    # If waiting for opponent in PvP
    if status == "waiting":
        board_rows: List[List[Any]] = []
        for rank in range(7, -1, -1):
            row = []
            for file in range(8):
                sq = chess.square(file, rank)
                piece = board.piece_at(sq)
                txt = _get_piece_glyph(piece)
                row.append(custom.Button.inline(txt, f"c_{game_id}_join".encode()))
            board_rows.append(row)
        board_rows.append([custom.Button.inline("⚔️ Join the Game", f"c_{game_id}_join".encode())])
        return board_rows

    # If promotion choice is requested
    if promotion_move:
        from_sq, to_sq = promotion_move
        turn_color = board.turn
        q_sym = "♕" if turn_color == chess.WHITE else "♛"
        r_sym = "♖" if turn_color == chess.WHITE else "♜"
        b_sym = "♗" if turn_color == chess.WHITE else "♝"
        n_sym = "♘" if turn_color == chess.WHITE else "♞"

        promo_row = [
            custom.Button.inline(f"{q_sym} Queen", f"c_{game_id}_pr_{from_sq}{to_sq}_q".encode()),
            custom.Button.inline(f"{r_sym} Rook", f"c_{game_id}_pr_{from_sq}{to_sq}_r".encode()),
            custom.Button.inline(f"{b_sym} Bishop", f"c_{game_id}_pr_{from_sq}{to_sq}_b".encode()),
            custom.Button.inline(f"{n_sym} Knight", f"c_{game_id}_pr_{from_sq}{to_sq}_n".encode()),
        ]
        cancel_row = [custom.Button.inline("🔙 Cancel Selection", f"c_{game_id}_cancel".encode())]
        return [promo_row, cancel_row]

    # Determine orientation (White at bottom vs Black at bottom)
    # Default is dynamic (current turn at bottom) or manually flipped
    flipped = game.get("flipped", False)
    is_white_turn = board.turn == chess.WHITE

    # If dynamic rotation: active player is at the bottom
    # White at bottom: ranks 7 down to 0, files 0 up to 7
    # Black at bottom: ranks 0 up to 7, files 7 down to 0
    white_at_bottom = is_white_turn if not flipped else (not is_white_turn)

    if white_at_bottom:
        ranks = list(range(7, -1, -1))
        files = list(range(8))
    else:
        ranks = list(range(8))
        files = list(range(7, -1, -1))

    # Pre-calculate legal destination squares for the currently selected piece
    dest_squares: Dict[int, bool] = {}  # sq -> is_capture
    if selected_sq:
        with contextlib.suppress(Exception):
            from_parsed = chess.parse_square(selected_sq)
            for m in board.legal_moves:
                if m.from_square == from_parsed:
                    dest_squares[m.to_square] = board.is_capture(m)

    board_rows = []
    for rank in ranks:
        row = []
        for file in files:
            sq = chess.square(file, rank)
            sq_name = chess.square_name(sq)
            piece = board.piece_at(sq)

            # Determine button display label
            if selected_sq and sq_name == selected_sq:
                # Highlight currently selected piece
                txt = f"[{_get_piece_glyph(piece)}]"
            elif sq in dest_squares:
                # Valid move destination
                is_cap = dest_squares[sq]
                if is_cap and piece:
                    txt = f"⚔{_get_piece_glyph(piece)}"
                elif is_cap:
                    txt = "⚔️"
                else:
                    txt = "•"
            elif piece:
                txt = _get_piece_glyph(piece)
            else:
                txt = " "

            # Compact callback query string (< 20 bytes)
            cb_data = f"c_{game_id}_{sq_name}".encode()
            row.append(custom.Button.inline(txt, cb_data))
        board_rows.append(row)

    # Action controls row under the 8x8 board
    controls = [
        custom.Button.inline("🏳️ Resign", f"c_{game_id}_rsgn".encode()),
        custom.Button.inline("🔄 Rotate", f"c_{game_id}_rot".encode()),
    ]
    board_rows.append(controls)
    return board_rows


async def _record_stat(user_id: int, result: str) -> None:
    col = _stats_col()
    field = f"chess_{result}"
    with contextlib.suppress(Exception):
        await col.find_one_and_update(
            {"_id": str(user_id)},
            {"$inc": {field: 1, "chess_total": 1}},
            upsert=True,
        )


# ─── Inline Query Handler for Assistant Bot ──────────────────────────────────

if getattr(Friday, "bot", None):

    @Friday.bot.on_inline_query(filters.regex(r"^chess"))
    @log_errors
    async def chess_inline_handler(c, iq):
        raw_text = (iq.text or "").strip()
        builder = iq.builder

        # 1. Matching existing game: "chess <game_id>"
        match = re.search(r"^chess\s+([a-zA-Z0-9_-]+)", raw_text)
        if match:
            game_id = match.group(1)
            col = _games_col()
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if game:
                text = _build_status_text(game)
                buttons = _render_chess_keyboard(game)
                result = builder.article(
                    title=f"Chess: {game.get('w_name', 'White')} vs {game.get('b_name', 'Black')}",
                    description=f"Turn: {'White' if chess.Board(game['fen']).turn == chess.WHITE else 'Black'}",
                    text=text,
                    parse_mode="html",
                    buttons=buttons,
                )
                return await iq.answer([result], cache_time=0)

        # 2. Interactive new game creation from inline query
        user_name = getattr(iq.sender, "first_name", "Player") or "Player"
        user_id = iq.sender_id

        # Card A: PvP Match
        pvp_id = uuid.uuid4().hex[:8]
        pvp_game = {
            "_id": f"chess_{pvp_id}",
            "game_id": pvp_id,
            "fen": chess.STARTING_FEN,
            "w_id": user_id,
            "w_name": user_name,
            "b_id": None,
            "b_name": "Challenger",
            "mode": "pvp",
            "status": "waiting",
            "last_move": None,
            "flipped": False,
            "created_at": time.time(),
        }
        await _games_col().insert_one(pvp_game)
        pvp_text = _build_status_text(pvp_game)
        pvp_buttons = _render_chess_keyboard(pvp_game)

        # Card B: vs AI Engine
        ai_id = uuid.uuid4().hex[:8]
        ai_game = {
            "_id": f"chess_{ai_id}",
            "game_id": ai_id,
            "fen": chess.STARTING_FEN,
            "w_id": user_id,
            "w_name": user_name,
            "b_id": None,
            "b_name": "Friday Engine",
            "mode": "ai",
            "status": "active",
            "last_move": None,
            "flipped": False,
            "created_at": time.time(),
        }
        await _games_col().insert_one(ai_game)
        ai_text = _build_status_text(ai_game)
        ai_buttons = _render_chess_keyboard(ai_game)

        results = [
            builder.article(
                title="♟️ Play Chess (PvP with Friend)",
                description=f"Start a match as White ({user_name}) vs Challenger",
                text=pvp_text,
                parse_mode="html",
                buttons=pvp_buttons,
            ),
            builder.article(
                title="🤖 Play Chess vs Friday AI",
                description="Instant solo match against the built-in chess engine",
                text=ai_text,
                parse_mode="html",
                buttons=ai_buttons,
            ),
        ]
        await iq.answer(results, cache_time=0)


@Friday.register_on_cmd(
    ["chess"],
    cmd_help={
        "help": "Play Chess with interactive 8x8 inline keyboard grid.",
        "example": [
            "chess",
            "chess ai",
            "chess @username",
            "chess e4",
            "chess stats",
        ],
    },
)
@log_errors
async def chess_cmd(c: Client, m: Message):
    arg = (m.user_input or "").strip()
    sender_id = m.sender_id
    chat_id = m.chat_id or sender_id
    col = _games_col()

    if arg == "stats":
        scol = _stats_col()
        doc = await scol.find_one({"_id": str(sender_id)}) or {}
        wins = doc.get("chess_wins", 0)
        losses = doc.get("chess_losses", 0)
        draws = doc.get("chess_draws", 0)
        total = doc.get("chess_total", 0)
        win_rate = round((wins / total) * 100, 1) if total else 0.0

        return await m.handle_message(
            f"📊 <b>Chess Record for You</b>\n\n"
            f"• <b>Total Games:</b> <code>{total}</code>\n"
            f"• <b>Wins:</b> 🟢 <code>{wins}</code>\n"
            f"• <b>Losses:</b> 🔴 <code>{losses}</code>\n"
            f"• <b>Draws:</b> 🟡 <code>{draws}</code>\n"
            f"• <b>Win Rate:</b> <code>{win_rate}%</code>"
        )

    # Check for direct text move input in chat: e.g. .chess e4, .chess e2e4, .chess move e2e4
    move_query = arg
    if move_query.startswith("move "):
        move_query = move_query.split("move ", 1)[1].strip()

    is_move_attempt = bool(
        move_query and not move_query.startswith(("@", "fen ")) and move_query not in ("pvp", "ai", "new", "help")
    )

    if is_move_attempt:
        active_game = await col.find_one({"chat_id": chat_id, "status": "active"})
        if not active_game:
            if arg.startswith("move "):
                return await m.handle_message(
                    "❌ <i>No active chess game in this chat. Start one with</i> <code>.chess</code>"
                )
        else:
            board = chess.Board(active_game["fen"])
            player_is_white = board.turn == chess.WHITE
            active_turn_id = active_game["w_id"] if player_is_white else active_game.get("b_id")

            if active_turn_id and sender_id != active_turn_id:
                return await m.handle_message("⏳ <i>It is not your turn!</i>")

            move = None
            with contextlib.suppress(Exception):
                move = board.parse_san(move_query)
            if not move:
                with contextlib.suppress(Exception):
                    move = chess.Move.from_uci(move_query)
            if not move and len(move_query) == 4:
                with contextlib.suppress(Exception):
                    move = chess.Move.from_uci(move_query + "q")

            if move and move in board.legal_moves:
                san_move = board.san(move)
                from_name = chess.square_name(move.from_square)
                to_name = chess.square_name(move.to_square)
                player_name = active_game["w_name"] if player_is_white else active_game["b_name"]
                p_text = f"👤 <b>{player_name}:</b> {from_name} ➔ {to_name} (<code>{san_move}</code>)"

                board.push(move)
                active_game["fen"] = board.fen()
                recent_moves = [p_text]

                if active_game["mode"] == "ai" and not board.is_game_over():
                    ai_move = _get_ai_move(board)
                    if ai_move:
                        ai_san = board.san(ai_move)
                        ai_from = chess.square_name(ai_move.from_square)
                        ai_to = chess.square_name(ai_move.to_square)
                        board.push(ai_move)
                        active_game["fen"] = board.fen()
                        recent_moves.append(f"🤖 <b>Friday Engine:</b> {ai_from} ➔ {ai_to} (<code>{ai_san}</code>)")

                active_game["last_move"] = "\n".join(recent_moves)

                if board.is_game_over():
                    active_game["status"] = "finished"

                await col.find_one_and_update(
                    {"_id": active_game["_id"]},
                    {
                        "$set": {
                            "fen": active_game["fen"],
                            "status": active_game["status"],
                            "last_move": active_game["last_move"],
                        }
                    },
                )

                text = _build_status_text(active_game)
                buttons = _render_chess_keyboard(active_game)
                await m.handle_message(text, buttons=buttons)
                return

    # Start new game setup
    game_id = uuid.uuid4().hex[:8]
    p1_name = getattr(getattr(m, "from_user", None), "first_name", None) or "Player"
    mode = "ai"
    b_id = None
    b_name = "Friday Engine"
    w_id = sender_id
    w_name = p1_name
    status = "active"

    # Check for PvP challenge or explicit AI
    if arg == "ai":
        mode = "ai"
        b_name = "Friday Engine"
        status = "active"
    elif arg == "pvp" or arg.startswith("@") or m.reply_to_message:
        target = None
        if m.reply_to_message:
            target = m.reply_to_message.sender
        elif arg.startswith("@"):
            with contextlib.suppress(Exception):
                target = await c.get_entity(arg)

        mode = "pvp"
        if target and getattr(target, "id", None) != sender_id:
            b_id = target.id
            b_name = getattr(target, "first_name", "Challenger")
            status = "active"
        elif target and getattr(target, "id", None) == sender_id:
            return await m.handle_message("😅 <i>You cannot challenge yourself!</i>")
        else:
            b_id = None
            b_name = "Challenger"
            status = "waiting"
    else:
        # Default in private chat -> AI, in group chat -> PvP waiting
        if m.is_private:
            mode = "ai"
            b_name = "Friday Engine"
            status = "active"
        else:
            mode = "pvp"
            b_id = None
            b_name = "Challenger"
            status = "waiting"

    starting_fen = chess.STARTING_FEN
    if arg.startswith("fen "):
        custom_fen = arg.split("fen ", 1)[1].strip()
        try:
            chess.Board(custom_fen)
            starting_fen = custom_fen
        except ValueError:
            return await m.handle_message("❌ <i>Invalid FEN string provided!</i>")

    game_data = {
        "_id": f"chess_{game_id}",
        "game_id": game_id,
        "chat_id": chat_id,
        "fen": starting_fen,
        "w_id": w_id,
        "w_name": w_name,
        "b_id": b_id,
        "b_name": b_name,
        "mode": mode,
        "status": status,
        "last_move": None,
        "flipped": False,
        "created_at": time.time(),
    }

    # Archive previous active game in this chat
    await col.update_many({"chat_id": chat_id, "status": "active"}, {"$set": {"status": "archived"}})
    await col.insert_one(game_data)

    text = _build_status_text(game_data)
    buttons = _render_chess_keyboard(game_data)

    # 1. Try inline query via assistant bot (renders inline buttons in userbot mode)
    sent = False
    if getattr(Friday, "bot_info", None) and getattr(Friday.bot_info, "username", None):
        try:
            results = await c.get_inline_bot_results(Friday.bot_info.username, f"chess {game_id}")
            if results:
                await results[0].click(chat_id)
                sent = True
                with contextlib.suppress(Exception):
                    await m.delete_if_self()
        except Exception as exc:
            logger.debug(f"Chess inline bot query failed: {exc}")

    # 2. Direct bot message fallback if assistant bot is in the chat
    if not sent and getattr(Friday, "_raw_bot", None):
        try:
            await Friday._raw_bot.send_message(chat_id, text, buttons=buttons, parse_mode="html")
            sent = True
            with contextlib.suppress(Exception):
                await m.delete_if_self()
        except Exception as exc:
            logger.debug(f"Chess bot direct send failed: {exc}")

    # 3. Fallback: message with move instructions
    if not sent:
        fallback_msg = (
            f"{text}\n\n"
            "💡 <i>Inline keyboard is unavailable. You can make moves by typing:</i>\n"
            "<code>.chess e4</code> or <code>.chess e2e4</code>"
        )
        await m.handle_message(fallback_msg)


if getattr(Friday, "bot", None):

    @Friday.bot.on_callback_query(pattern=r"^(?:c_|chess_)")
    async def chess_callback(c, cq):
        data = cq.data.decode("utf-8") if isinstance(cq.data, bytes) else str(cq.data)
        col = _games_col()
        clicker_id = cq.sender_id
        clicker_name = getattr(getattr(cq, "sender", None), "first_name", None) or "Player"

        # ── Start New Game ──
        if data.startswith("c_new_") or data.startswith("chess_new#"):
            mode = "ai" if "ai" in data else "pvp"
            game_id = uuid.uuid4().hex[:8]
            game_data = {
                "_id": f"chess_{game_id}",
                "game_id": game_id,
                "chat_id": cq.chat_id or clicker_id,
                "fen": chess.STARTING_FEN,
                "w_id": clicker_id,
                "w_name": clicker_name,
                "b_id": None if mode == "pvp" else None,
                "b_name": "Friday Engine" if mode == "ai" else "Challenger",
                "mode": mode,
                "status": "waiting" if mode == "pvp" else "active",
                "last_move": None,
                "flipped": False,
                "created_at": time.time(),
            }
            await col.insert_one(game_data)
            _GAME_SELECTION.pop(game_id, None)
            _GAME_PROMOTIONS.pop(game_id, None)

            text = _build_status_text(game_data)
            buttons = _render_chess_keyboard(game_data)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer("New game started!")

        # ── Join PvP Match ──
        if re.search(r"^c_([a-zA-Z0-9]+)_join$", data):
            game_id = re.search(r"^c_([a-zA-Z0-9]+)_join$", data).group(1)
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if not game or game.get("status") != "waiting":
                return await cq.answer("Game already joined or ended.", alert=True)

            if clicker_id == game["w_id"]:
                return await cq.answer("You are already White! Wait for someone else to join.", alert=True)

            game["b_id"] = clicker_id
            game["b_name"] = clicker_name
            game["status"] = "active"

            await col.find_one_and_update(
                {"_id": f"chess_{game_id}"}, {"$set": {"b_id": clicker_id, "b_name": clicker_name, "status": "active"}}
            )

            text = _build_status_text(game)
            buttons = _render_chess_keyboard(game)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer(f"Joined as Black! Good luck, {clicker_name}.")

        # ── Rotate Board ──
        if re.search(r"^c_([a-zA-Z0-9]+)_rot$", data):
            game_id = re.search(r"^c_([a-zA-Z0-9]+)_rot$", data).group(1)
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if not game:
                return await cq.answer("Game not found.")

            flipped = not game.get("flipped", False)
            game["flipped"] = flipped
            await col.find_one_and_update({"_id": f"chess_{game_id}"}, {"$set": {"flipped": flipped}})

            selected_sq = _GAME_SELECTION.get(game_id)
            promo = _GAME_PROMOTIONS.get(game_id)
            text = _build_status_text(game, selected_sq=selected_sq)
            buttons = _render_chess_keyboard(game, selected_sq=selected_sq, promotion_move=promo)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer("Board rotated.")

        # ── Resign Match ──
        if re.search(r"^(?:c|chess)_([a-zA-Z0-9]+)_rsgn$", data) or data.startswith("chess_resign#"):
            match = re.search(r"^(?:c|chess)_([a-zA-Z0-9]+)_rsgn$", data)
            game_id = match.group(1) if match else data.split("#", 1)[1]
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if not game or game.get("status") != "active":
                return await cq.answer("Game already ended.")

            if clicker_id not in (game["w_id"], game.get("b_id")):
                return await cq.answer("⛔ You are not playing in this match!", alert=True)

            resigner = game["w_name"] if clicker_id == game["w_id"] else game["b_name"]
            winner = game["b_name"] if clicker_id == game["w_id"] else game["w_name"]

            await col.find_one_and_update({"_id": f"chess_{game_id}"}, {"$set": {"status": "forfeit"}})

            await _record_stat(clicker_id, "losses")
            winner_id = game["b_id"] if clicker_id == game["w_id"] else game["w_id"]
            if winner_id:
                await _record_stat(winner_id, "wins")

            game["status"] = "forfeit"
            _GAME_SELECTION.pop(game_id, None)
            _GAME_PROMOTIONS.pop(game_id, None)

            text = _build_status_text(game)
            buttons = _render_chess_keyboard(game)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer(f"{resigner} resigned. {winner} wins!")

        # ── Cancel Selection / Promotion ──
        if re.search(r"^c_([a-zA-Z0-9]+)_cancel$", data) or data.startswith("chess_cancel#"):
            match = re.search(r"^c_([a-zA-Z0-9]+)_cancel$", data)
            game_id = match.group(1) if match else data.split("#", 1)[1]
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if not game:
                return await cq.answer("Game not found.")

            _GAME_SELECTION.pop(game_id, None)
            _GAME_PROMOTIONS.pop(game_id, None)

            text = _build_status_text(game)
            buttons = _render_chess_keyboard(game)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer("Selection cleared.")

        # ── Promotion Selection: c_<game_id>_pr_<from><to>_<piece> ──
        promo_match = re.search(r"^c_([a-zA-Z0-9]+)_pr_([a-h][1-8])([a-h][1-8])_([qrnb])$", data)
        if promo_match:
            game_id, from_sq, to_sq, piece_char = promo_match.groups()
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if not game or game.get("status") != "active":
                return await cq.answer("Game is finished.")

            board = chess.Board(game["fen"])
            is_white = board.turn == chess.WHITE
            active_turn_id = game["w_id"] if is_white else game.get("b_id")

            if active_turn_id and clicker_id != active_turn_id:
                return await cq.answer("⏳ Not your turn!", alert=True)

            promo_type = {
                "q": chess.QUEEN,
                "r": chess.ROOK,
                "b": chess.BISHOP,
                "n": chess.KNIGHT,
            }.get(piece_char, chess.QUEEN)

            move = chess.Move(chess.parse_square(from_sq), chess.parse_square(to_sq), promotion=promo_type)
            if move not in board.legal_moves:
                _GAME_PROMOTIONS.pop(game_id, None)
                _GAME_SELECTION.pop(game_id, None)
                return await cq.answer("Illegal move!", alert=True)

            san = board.san(move)
            player_name = game["w_name"] if is_white else game["b_name"]
            p_text = f"👤 <b>{player_name}:</b> {from_sq} ➔ {to_sq} (<code>{san}</code>)"

            board.push(move)
            game["fen"] = board.fen()
            recent_moves = [p_text]

            _GAME_PROMOTIONS.pop(game_id, None)
            _GAME_SELECTION.pop(game_id, None)

            if game["mode"] == "ai" and not board.is_game_over():
                ai_move = _get_ai_move(board)
                if ai_move:
                    ai_san = board.san(ai_move)
                    ai_from = chess.square_name(ai_move.from_square)
                    ai_to = chess.square_name(ai_move.to_square)
                    board.push(ai_move)
                    game["fen"] = board.fen()
                    recent_moves.append(f"🤖 <b>Friday Engine:</b> {ai_from} ➔ {ai_to} (<code>{ai_san}</code>)")

            game["last_move"] = "\n".join(recent_moves)

            if board.is_game_over():
                game["status"] = "finished"
                if board.is_checkmate():
                    if board.turn == chess.WHITE:
                        if game["b_id"]:
                            await _record_stat(game["b_id"], "wins")
                        await _record_stat(game["w_id"], "losses")
                    else:
                        await _record_stat(game["w_id"], "wins")
                        if game["b_id"]:
                            await _record_stat(game["b_id"], "losses")
                else:
                    await _record_stat(game["w_id"], "draws")
                    if game["b_id"]:
                        await _record_stat(game["b_id"], "draws")

            await col.find_one_and_update(
                {"_id": f"chess_{game_id}"},
                {
                    "$set": {
                        "fen": game["fen"],
                        "status": game["status"],
                        "last_move": game["last_move"],
                    }
                },
            )

            text = _build_status_text(game)
            buttons = _render_chess_keyboard(game)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer(f"Promoted to {piece_char.upper()}! {from_sq} ➔ {to_sq}")

        # ── Square Click: c_<game_id>_<square> ──
        sq_match = re.search(r"^c_([a-zA-Z0-9]+)_([a-h][1-8])$", data)
        if sq_match:
            game_id, clicked_sq = sq_match.groups()
            game = await col.find_one({"_id": f"chess_{game_id}"})
            if not game or game.get("status") != "active":
                return await cq.answer("Game is finished.")

            board = chess.Board(game["fen"])
            is_white = board.turn == chess.WHITE
            active_turn_id = game["w_id"] if is_white else game.get("b_id")

            # Check if player is authorized
            if game["mode"] == "pvp":
                if clicker_id not in (game["w_id"], game.get("b_id")):
                    return await cq.answer("⛔ You are not playing in this match!", alert=True)
                if active_turn_id and clicker_id != active_turn_id:
                    return await cq.answer("⏳ Wait, please! Now is not your turn.")
            elif game["mode"] == "ai":
                if clicker_id != game["w_id"]:
                    return await cq.answer("⛔ This is someone else's game!", alert=True)

            selected_sq = _GAME_SELECTION.get(game_id)
            clicked_parsed = chess.parse_square(clicked_sq)
            piece_at_clicked = board.piece_at(clicked_parsed)

            # ── Case 1: No piece currently selected ──
            if not selected_sq:
                if not piece_at_clicked:
                    return await cq.answer()

                if piece_at_clicked.color != board.turn:
                    return await cq.answer("That is not your piece!")

                # Check if piece has legal moves
                moves = [m for m in board.legal_moves if m.from_square == clicked_parsed]
                if not moves:
                    p_name = _PIECE_NAMES.get(piece_at_clicked.piece_type, "Piece")
                    return await cq.answer(f"{p_name} at {clicked_sq} has no legal moves.")

                _GAME_SELECTION[game_id] = clicked_sq
                text = _build_status_text(game, selected_sq=clicked_sq)
                buttons = _render_chess_keyboard(game, selected_sq=clicked_sq)
                with contextlib.suppress(Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")
                p_name = _PIECE_NAMES.get(piece_at_clicked.piece_type, "Piece")
                return await cq.answer(f"{p_name} ({clicked_sq}) selected")

            # ── Case 2: A piece was already selected ──
            # Subcase A: Clicked same square again -> Deselect
            if clicked_sq == selected_sq:
                _GAME_SELECTION[game_id] = None
                text = _build_status_text(game, selected_sq=None)
                buttons = _render_chess_keyboard(game, selected_sq=None)
                with contextlib.suppress(Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")
                return await cq.answer("Deselected.")

            # Subcase B: Clicked another of player's own pieces -> Switch selection
            if piece_at_clicked and piece_at_clicked.color == board.turn:
                moves = [m for m in board.legal_moves if m.from_square == clicked_parsed]
                if not moves:
                    p_name = _PIECE_NAMES.get(piece_at_clicked.piece_type, "Piece")
                    return await cq.answer(f"{p_name} at {clicked_sq} has no legal moves.")

                _GAME_SELECTION[game_id] = clicked_sq
                text = _build_status_text(game, selected_sq=clicked_sq)
                buttons = _render_chess_keyboard(game, selected_sq=clicked_sq)
                with contextlib.suppress(Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")
                p_name = _PIECE_NAMES.get(piece_at_clicked.piece_type, "Piece")
                return await cq.answer(f"{p_name} ({clicked_sq}) selected")

            # Subcase C: Attempting a move from selected_sq to clicked_sq
            from_parsed = chess.parse_square(selected_sq)
            to_parsed = clicked_parsed

            # Check for pawn promotion
            from_piece = board.piece_at(from_parsed)
            is_pawn = from_piece and from_piece.piece_type == chess.PAWN
            to_rank = chess.square_rank(to_parsed)
            if is_pawn and (to_rank == 7 or to_rank == 0):
                promo_candidates = [
                    m
                    for m in board.legal_moves
                    if m.from_square == from_parsed and m.to_square == to_parsed and m.promotion
                ]
                if promo_candidates:
                    _GAME_PROMOTIONS[game_id] = (selected_sq, clicked_sq)
                    text = _build_status_text(game, selected_sq=selected_sq)
                    buttons = _render_chess_keyboard(
                        game,
                        selected_sq=selected_sq,
                        promotion_move=(selected_sq, clicked_sq),
                    )
                    with contextlib.suppress(Exception):
                        await cq.edit(text, buttons=buttons, parse_mode="html")
                    return await cq.answer("Choose promotion piece!")

            # Normal move lookup
            target_move = None
            for m in board.legal_moves:
                if m.from_square == from_parsed and m.to_square == to_parsed:
                    target_move = m
                    break

            if not target_move:
                # Cancel selection if clicking an invalid square
                _GAME_SELECTION[game_id] = None
                text = _build_status_text(game, selected_sq=None)
                buttons = _render_chess_keyboard(game, selected_sq=None)
                with contextlib.suppress(Exception):
                    await cq.edit(text, buttons=buttons, parse_mode="html")
                return await cq.answer()

            # Execute legal move
            _GAME_SELECTION[game_id] = None
            _GAME_PROMOTIONS.pop(game_id, None)

            san = board.san(target_move)
            player_name = game["w_name"] if is_white else game["b_name"]
            p_text = f"👤 <b>{player_name}:</b> {selected_sq} ➔ {clicked_sq} (<code>{san}</code>)"

            board.push(target_move)
            game["fen"] = board.fen()
            recent_moves = [p_text]

            # AI response
            if game["mode"] == "ai" and not board.is_game_over():
                ai_move = _get_ai_move(board)
                if ai_move:
                    ai_san = board.san(ai_move)
                    ai_from = chess.square_name(ai_move.from_square)
                    ai_to = chess.square_name(ai_move.to_square)
                    board.push(ai_move)
                    game["fen"] = board.fen()
                    recent_moves.append(f"🤖 <b>Friday Engine:</b> {ai_from} ➔ {ai_to} (<code>{ai_san}</code>)")

            game["last_move"] = "\n".join(recent_moves)

            if board.is_game_over():
                game["status"] = "finished"
                if board.is_checkmate():
                    if board.turn == chess.WHITE:
                        if game["b_id"]:
                            await _record_stat(game["b_id"], "wins")
                        await _record_stat(game["w_id"], "losses")
                    else:
                        await _record_stat(game["w_id"], "wins")
                        if game["b_id"]:
                            await _record_stat(game["b_id"], "losses")
                else:
                    await _record_stat(game["w_id"], "draws")
                    if game["b_id"]:
                        await _record_stat(game["b_id"], "draws")

            await col.find_one_and_update(
                {"_id": f"chess_{game_id}"},
                {
                    "$set": {
                        "fen": game["fen"],
                        "status": game["status"],
                        "last_move": game["last_move"],
                    }
                },
            )

            text = _build_status_text(game)
            buttons = _render_chess_keyboard(game)
            with contextlib.suppress(Exception):
                await cq.edit(text, buttons=buttons, parse_mode="html")
            return await cq.answer(f"{selected_sq} ➔ {clicked_sq}")

        await cq.answer()
