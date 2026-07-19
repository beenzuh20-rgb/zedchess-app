"""
Authoritative chess-clock engine.

Design
------
The clock is *derived*, never mutated blindly. The database stores the
"banked" remaining time for each side plus the wall-clock instant at which the
currently-active player's turn began (``clock_started_at``). The *live* remaining
time is always computed from those two values against the real clock:

    live_remaining(active) = banked[active] - (now - clock_started_at)

This makes the clock:

* Accurate under latency / inactive tabs / CPU load — it is a pure function of
  wall-clock time, not of how often the server happened to tick.
* Refresh-safe — a fresh page load just re-reads the stored values and resumes.
* Disconnect-safe — the server keeps counting (wall clock) regardless of sockets.
* Cheat-proof — clients only ever *receive* computed values; they never send time.

Transitions happen only on a *legal move* (handled in ``game_service.apply_move``)
or on *timeout* (handled by the ticker in ``sockets.handlers``).

All functions here are pure with respect to I/O: they take a ``Game`` row and an
optional ``now`` timestamp (epoch seconds, float) and return/modify numbers.
"""

import time


def now_seconds() -> float:
    """Current epoch time in seconds (monotonic-ish wall clock)."""
    return time.time()


def live_clocks(game, now: float | None = None) -> tuple[int, int]:
    """Return (white_ms, black_ms) as they are *right now*.

    The currently-active player's banked time is decremented by the elapsed
    time since their turn started. The inactive player shows their banked value.
    If the game is not active (finished/aborted) the stored banked values are
    returned untouched.
    """
    if now is None:
        now = now_seconds()
    white = game.white_clock_ms
    black = game.black_clock_ms
    if game.status == "active" and game.clock_started_at is not None:
        elapsed_ms = int((now - game.clock_started_at) * 1000)
        if elapsed_ms < 0:
            elapsed_ms = 0
        if game.turn_color() == "white":
            white = max(0, white - elapsed_ms)
        else:
            black = max(0, black - elapsed_ms)
    return white, black


def active_remaining_ms(game, now: float | None = None) -> int:
    """Remaining time (ms) for the player whose turn it is, right now."""
    white, black = live_clocks(game, now)
    return white if game.turn_color() == "white" else black


def bank_active_clock(game, now: float | None = None) -> int:
    """Fold the active player's elapsed running time back into their banked value.

    Call this *before* recording a move. Returns the banked remaining time of the
    active player (may be ``0`` or negative if their flag has fallen).
    """
    if now is None:
        now = now_seconds()
    if game.clock_started_at is None:
        # Clock not started yet (e.g. waiting state) — nothing to fold in.
        return game.white_clock_ms if game.turn_color() == "white" else game.black_clock_ms
    elapsed_ms = int((now - game.clock_started_at) * 1000)
    if elapsed_ms < 0:
        elapsed_ms = 0
    if game.turn_color() == "white":
        game.white_clock_ms = max(0, game.white_clock_ms - elapsed_ms)
        return game.white_clock_ms
    game.black_clock_ms = max(0, game.black_clock_ms - elapsed_ms)
    return game.black_clock_ms


def has_flag_fallen(game, now: float | None = None) -> bool:
    """True if the active player's clock has reached zero."""
    return active_remaining_ms(game, now) <= 0


def start_clock(game, now: float | None = None) -> None:
    """Mark the clock as running from ``now`` (White to move first, like Lichess)."""
    game.clock_started_at = now if now is not None else now_seconds()


def switch_after_move(game, increment_ms: int, now: float | None = None) -> None:
    """Apply the increment to the mover and (if the clock is live) hand the
    tick to the opponent.

    Pre-condition: ``bank_active_clock`` has already been called for this move,
    so the mover's banked value reflects the time they actually used.

    Clock-start rule (move-based, like many casual chess apps):
    * Before either side has moved, the clock is NOT running.
    * White's first move: both clocks stay still (increment is banked, but the
      clock does not start).
    * Black's first move: the clock starts now — White's clock begins ticking.
    * Every subsequent move: the opponent's clock starts immediately.
    """
    if now is None:
        now = now_seconds()
    if game.turn_color() == "white":
        game.white_clock_ms += increment_ms
    else:
        game.black_clock_ms += increment_ms
    # The clock only begins once both players have moved at least once (i.e. the
    # game has reached its 2nd ply). Until then both clocks remain frozen.
    ply_count = len(game.moves.split()) if game.moves else 0
    if ply_count >= 2:
        game.clock_started_at = now


def is_clock_running(game) -> bool:
    """True once the clock is actually counting (both sides have moved)."""
    return game.status == "active" and game.clock_started_at is not None


def clock_payload(game, server_time_ms: int | None = None) -> dict:
    """Compact payload broadcast to clients for smooth client-side interpolation.

    ``white_clock_ms`` / ``black_clock_ms`` are the *banked* values (as stored),
    and ``server_time`` is the epoch millisecond at which those banked values
    were true. The client subtracts elapsed time from the *active* side only,
    and only while ``running`` is true (both sides have moved once).
    """
    if server_time_ms is None:
        server_time_ms = int(now_seconds() * 1000)
    return {
        "white_clock_ms": game.white_clock_ms,
        "black_clock_ms": game.black_clock_ms,
        "turn": game.turn_color(),
        "running": is_clock_running(game),
        "server_time": server_time_ms,
    }
