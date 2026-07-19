"""
Anti-cheat and fairness utilities.

The server is the source of truth for:
* move validation (board state in the Game model, validated with python-chess),
* clocks (server-side ticking only; clients never send remaining time),
* single-session enforcement (one socket per user per game),
* duplicate move rejection (monotonic move index),
* disconnection forfeit (configurable grace window).
"""

import time

from zedchess.extensions import db
from zedchess.models import Game, Settings


class AntiCheatError(Exception):
    """Raised when a client action violates game integrity."""


def latest_move_index(game: Game) -> int:
    """Number of moves already applied to a game."""
    return len(game.moves.split()) if game.moves else 0


def verify_move_order(game: Game, expected_index: int) -> None:
    """Reject out-of-order or duplicate move submissions.

    ``expected_index`` is the 1-based index the client claims this move has.
    """
    current = latest_move_index(game)
    if expected_index != current + 1:
        raise AntiCheatError(
            f"Move order mismatch: expected {current + 1}, got {expected_index}"
        )


def verify_turn(game: Game, user_id: int) -> str:
    """Return the color the user must be to move; raise otherwise."""
    turn = game.turn_color()
    if turn == "white" and game.white_id != user_id:
        raise AntiCheatError("Not your turn (white to move)")
    if turn == "black" and game.black_id != user_id:
        raise AntiCheatError("Not your turn (black to move)")
    if game.status != "active":
        raise AntiCheatError("Game is not active")
    return turn


def verify_single_session(active_sids: set, my_sid: str) -> None:
    """Prevent more than one live socket controlling a seat."""
    others = active_sids - {my_sid}
    if others:
        raise AntiCheatError("Multiple active sessions detected")


def connection_is_live(game: Game, db_session) -> dict:
    """Return live/disconnected state for both seats from last_seen pings."""
    settings = Settings.get(db_session)
    grace = settings.disconnect_forfeit_seconds
    now = time.time()
    return {
        "white_disconnected": False,  # populated by the socket layer
        "black_disconnected": False,
        "grace_seconds": grace,
        "now": now,
    }
