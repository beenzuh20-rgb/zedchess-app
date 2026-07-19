"""
Game engine service.

This is the authoritative chess brain. It owns:
* board state via ``python-chess`` (move validation, draw detection, PGN/FEN),
* applying a move and ticking the server clock + increment,
* termination detection (checkmate, draw rules, timeout, resignation, etc.),
* payout + Elo resolution on game end.

The SocketIO handlers are thin wrappers that authenticate, validate the seat,
then delegate to these functions. The client never decides legality, time, or
the winner.
"""

import time

import chess

from zedchess.extensions import db
from zedchess.models import Game, User, Settings
from zedchess.services.elo_service import update_ratings, update_draw
from zedchess.services.wallet_service import (
    unlock_refund,
    payout_winner,
)
from zedchess.services import notification_service as notes
from zedchess.utils.time_controls import parse_time_control


def _board(game: Game) -> chess.Board:
    board = chess.Board()
    if game.start_fen and game.start_fen not in ("startpos", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"):
        try:
            board = chess.Board(game.start_fen)
        except ValueError:
            board = chess.Board()
    for san in (game.moves.split() if game.moves else []):
        try:
            board.push_san(san)
        except ValueError:
            break
    return board


def legal_targets(game: Game, from_sq: str) -> list[str]:
    """UCI target squares (to-squares) for a given from-square, for the side to move."""
    board = _board(game)
    # Only the side to move can have legal moves from the selected square.
    if from_sq:
        piece = board.piece_at(chess.parse_square(from_sq))
        if piece is None:
            return []
        side_to_move = chess.WHITE if board.turn == chess.WHITE else chess.BLACK
        if piece.color != side_to_move:
            return []
    out = []
    for move in board.legal_moves:
        if move.uci()[:2] == from_sq:
            out.append(move.uci())
    return out


def uci_to_san(game: Game, uci: str) -> str:
    """Convert a UCI move string (e.g. 'e2e4', 'e7e8q') to SAN for the game."""
    board = _board(game)
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise ValueError(f"Illegal move: {uci}")
    return board.san(move)


def legal_moves(game: Game, color: str) -> list[str]:
    """UCI legal moves for the given color (used for client highlighting)."""
    board = _board(game)
    out = []
    for move in board.legal_moves:
        if board.turn == chess.WHITE and color == "white":
            out.append(move.uci())
        elif board.turn == chess.BLACK and color == "black":
            out.append(move.uci())
    return out


def apply_move(game: Game, san: str, index: int) -> dict:
    """Validate and apply a move, then advance the clock.

    The clock transition is fully delegated to :mod:`clock_service` so that:
    * the mover's elapsed running time is folded back into their banked time,
    * their increment is credited immediately,
    * the opponent's clock starts the instant the move is recorded,
    * and a flag-fall is detected before the move is counted.

    Returns a dict describing the new game state for broadcasting.
    """
    from zedchess.services.clock_service import (
        bank_active_clock, switch_after_move, has_flag_fallen, now_seconds,
    )

    board = _board(game)

    # Reject stale/out-of-order submissions (anti-cheat / duplicate guard).
    expected = len(game.moves.split()) if game.moves else 0
    if index != expected + 1:
        raise ValueError("Move order mismatch")

    # python-chess validates legality for us.
    try:
        board.push_san(san)
    except ValueError:
        raise ValueError(f"Illegal move: {san}")

    now = now_seconds()

    # Fold the mover's running time back into their banked clock.
    bank_active_clock(game, now)

    # If the mover's flag had already fallen, they lose on time — the move is
    # not counted.
    if has_flag_fallen(game, now):
        state = timeout_for(game, game.turn_color())
        return state

    game.moves = (game.moves + " " + san).strip()
    game.pgn = _build_pgn(game)
    game.fen = board.fen()

    # Credit increment to the mover and start the opponent's clock immediately.
    tc = parse_time_control(game.time_control)
    switch_after_move(game, tc.increment_ms, now)

    game.status = "active"
    if game.started_at is None:
        from datetime import datetime, timezone
        game.started_at = datetime.now(timezone.utc)

    # ---- Termination checks -------------------------------------------
    result = _check_termination(game, board)
    if result:
        _finish(game, board, result)

    db.session.commit()
    return _state_payload(game)


def _check_termination(game: Game, board: chess.Board) -> dict | None:
    """Return a result dict or None if the game continues."""
    if board.is_checkmate():
        winner = "black" if board.turn == chess.WHITE else "white"
        return {"result": winner, "termination": "checkmate"}
    if board.is_stalemate():
        return {"result": "draw", "termination": "stalemate"}
    if board.is_insufficient_material():
        return {"result": "draw", "termination": "insufficient"}
    if board.can_claim_fifty_moves():
        return {"result": "draw", "termination": "fifty_move"}
    if board.is_repetition(3):
        return {"result": "draw", "termination": "threefold"}
    return None


def timeout_for(game: Game, color: str) -> dict:
    """Flag a player as lost on time."""
    if game.status != "active":
        return _state_payload(game)
    winner = "black" if color == "white" else "white"
    result = {"result": winner, "termination": "timeout"}
    _finish(game, _board(game), result)
    db.session.commit()
    return _state_payload(game)


def resign(game: Game, color: str) -> dict:
    if game.status != "active":
        return _state_payload(game)
    winner = "black" if color == "white" else "white"
    _finish(game, _board(game), {"result": winner, "termination": "resignation"})
    db.session.commit()
    return _state_payload(game)


def agree_draw(game: Game) -> dict:
    if game.status != "active":
        return _state_payload(game)
    _finish(game, _board(game), {"result": "draw", "termination": "draw_agreed"})
    db.session.commit()
    return _state_payload(game)


def abort(game: Game, reason: str = "abort") -> dict:
    """Abort (no result) and refund stakes; used on disconnect/early exit."""
    if game.status in ("finished", "aborted"):
        return _state_payload(game)
    game.status = "aborted"
    game.termination = reason
    from datetime import datetime, timezone
    game.finished_at = datetime.now(timezone.utc)
    # Refund both stakes.
    if game.stake > 0:
        if game.white_id:
            unlock_refund(game.white_id, game.stake, game.room_id)
        if game.black_id:
            unlock_refund(game.black_id, game.stake, game.room_id)
    db.session.commit()
    return _state_payload(game)


def _finish(game: Game, board: chess.Board, result: dict) -> None:
    """Persist the result, distribute the pot and update ratings."""
    from datetime import datetime, timezone

    game.status = "finished"
    game.result = result["result"]
    game.termination = result["termination"]
    game.pgn = _build_pgn(game)
    game.finished_at = datetime.now(timezone.utc)
    if game.started_at:
        start = game.started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        game.duration_seconds = int(
            (game.finished_at - start).total_seconds()
        )

    white = db.session.get(User, game.white_id) if game.white_id else None
    black = db.session.get(User, game.black_id) if game.black_id else None

    # Stats + ratings (only for rated games with two real players).
    if white and black and game.rated:
        white.games_played += 1
        black.games_played += 1
        if result["result"] == "white":
            white.wins += 1
            black.losses += 1
            update_ratings(white, black)
        elif result["result"] == "black":
            black.wins += 1
            white.losses += 1
            update_ratings(black, white)
        else:
            white.draws += 1
            black.draws += 1
            update_draw(white, black)

    # ---- Betting payout ------------------------------------------------
    if game.stake > 0 and not game.payout_done:
        if result["result"] in ("white", "black"):
            winner_user = white if result["result"] == "white" else black
            loser_user = black if result["result"] == "white" else white
            # Release loser's locked stake back conceptually, then pay winner.
            commission = round(game.pot * game.commission_rate, 2)
            net = round(game.pot - commission, 2)
            if loser_user:
                unlock_refund(loser_user.id, game.stake, game.room_id)
            payout_winner(winner_user.id, net, game.room_id)
            game.payout_done = True
            notes.notify(
                winner_user.id, "victory",
                f"You won {net:.2f} from {game.room_id}!",
                {"room_id": game.room_id, "amount": net},
            )
            if loser_user:
                notes.notify(
                    loser_user.id, "defeat",
                    f"You lost your stake in {game.room_id}.",
                    {"room_id": game.room_id},
                )
        else:
            # Draw: refund both stakes.
            if white:
                unlock_refund(white.id, game.stake, game.room_id)
            if black:
                unlock_refund(black.id, game.stake, game.room_id)


def _build_pgn(game_model: Game, board: chess.Board = None) -> str:
    """Build a PGN string from headers + SAN moves.

    Builds a proper move-numbered PGN body. We iterate SAN pairs and number
    them; the final move is suffixed with ``#``/``=`` markers aren't required
    for storage/replay, but we keep the SAN as played (already includes ``#``).
    """
    sans = game_model.moves.split() if game_model.moves else []
    body_lines = []
    i = 0
    while i < len(sans):
        move_no = i // 2 + 1
        white = sans[i] if i < len(sans) else ""
        black = sans[i + 1] if i + 1 < len(sans) else ""
        body_lines.append(f"{move_no}. {white} {black}".rstrip())
        i += 2
    result_token = {"white": "1-0", "black": "0-1", "draw": "1/2-1/2"}.get(
        game_model.result, "*"
    )
    body = "\n".join(body_lines)
    if body:
        body += f" {result_token}"
    else:
        body = result_token
    headers = [
        '[Event "ZedChess"]',
        '[Site "zedchess.app"]',
        '[Date "' + (game_model.started_at.strftime("%Y.%m.%d")
                     if game_model.started_at else "????.??.??") + '"]',
        '[Round "-"]',
        '[White "' + (game_model.white_player.username
                      if game_model.white_player else "?") + '"]',
        '[Black "' + (game_model.black_player.username
                      if game_model.black_player else "?") + '"]',
        '[Result "' + result_token + '"]',
        '[TimeControl "' + game_model.time_control + '"]',
    ]
    return "\n".join(headers) + "\n\n" + body + "\n"


def _state_payload(game: Game) -> dict:
    """Compact, serialisable snapshot broadcast to clients."""
    from zedchess.services.clock_service import now_seconds
    return {
        "room_id": game.room_id,
        "moves": game.moves.split() if game.moves else [],
        "fen": game.fen,
        "server_time": int(now_seconds() * 1000),
        "turn": game.turn_color(),
        "white_clock_ms": game.white_clock_ms,
        "black_clock_ms": game.black_clock_ms,
        "white_id": game.white_id,
        "black_id": game.black_id,
        "stake": game.stake,
        "status": game.status,
        "result": game.result,
        "termination": game.termination,
        "rated": game.rated,
        "time_control": game.time_control,
    }
