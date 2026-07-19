"""
SocketIO handlers — the real-time core of ZedChess.

Two namespaces are used conceptually:
* lobby events  -> public lobby (challenges, online users, chat, friends)
* game events   -> per-game room ``game:<room_id>`` (moves, clocks, resign)

The server is authoritative for:
* who is online (tracked in ``online_users`` keyed by user id),
* which socket owns which game seat (``game_sids``),
* clock ticking — a background thread decrements the active player's clock and
  broadcasts it; clients never send their own remaining time.
"""

import time
import json
import threading

from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room

from zedchess.extensions import db, socketio
from zedchess.models import (
    User, Game, Challenge, Message, Notification, Friendship, Settings,
)
from zedchess.services import notification_service as notes
from zedchess.services.wallet_service import lock_stake, unlock_refund
from zedchess.services.game_service import (
    apply_move, timeout_for, resign as resign_game, agree_draw, abort as abort_game,
    uci_to_san,
)
from zedchess.utils.time_controls import parse_time_control
from zedchess.utils.anti_cheat import verify_move_order, verify_turn
from zedchess.utils.security import sanitize_text

# ---------------------------------------------------------------------------
# In-memory realtime state (swap for Redis in multi-worker prod)
# ---------------------------------------------------------------------------
# user_id -> set of sids
online_users: dict[int, set] = {}
# game room_id -> {user_id: sid} for the two seats
game_sids: dict[str, dict] = {}
# game room_id -> {user_id: last_ping_ts}
game_last_seen: dict[str, dict] = {}
# challenge id -> set of sids watching
# (lobby broadcast handled via public channel)
state_lock = threading.Lock()


def register_socket_handlers(socketio) -> None:
    """Attach all SocketIO event handlers."""

    # ------------------------------------------------------------------
    @socketio.on("connect")
    def on_connect(auth):
        if not current_user.is_authenticated:
            return False  # reject anonymous sockets
        with state_lock:
            sids = online_users.setdefault(current_user.id, set())
            sids.add(request.sid)
        user = db.session.get(User, current_user.id)
        if user:
            user.online = True
            db.session.commit()
        # Join rooms FIRST so the new socket receives the broadcasts below.
        join_room("lobby")
        # Personal room for targeted notifications.
        join_room(f"user_{current_user.id}")
        # Push the current lobby state to everyone (so a refreshed client
        # immediately repopulates challenges + online players).
        _broadcast_challenges()
        socketio.emit("lobby:online", public_online(), to="lobby")

    @socketio.on("disconnect")
    def on_disconnect():
        if not current_user.is_authenticated:
            return
        uid = current_user.id
        with state_lock:
            sids = online_users.get(uid)
            if sids:
                sids.discard(request.sid)
                if not sids:
                    online_users.pop(uid, None)
        # Detach from any game seat.
        _detach_from_games(request.sid, uid)
        # If fully offline, mark offline (grace handled by game thread).
        if uid not in online_users:
            user = db.session.get(User, uid)
            if user:
                user.online = False
                db.session.commit()
        socketio.emit("lobby:online", public_online(), to="lobby")

    @socketio.on("lobby:ping_presence")
    def lobby_ping_presence():
        # Client reconnected; refresh the online roster for everyone.
        socketio.emit("lobby:online", public_online(), to="lobby")

    @socketio.on("lobby:request_state")
    def lobby_request_state():
        # Defensive: client asks for a fresh snapshot (covers connect races).
        _broadcast_challenges()
        socketio.emit("lobby:online", public_online(), to=request.sid)

    # ===================== LOBBY =====================
    @socketio.on("lobby:challenge_create")
    def lobby_create_challenge(data):
        """Create a challenge from the lobby in real time."""
        if not current_user.is_authenticated:
            return
        tc = (data or {}).get("time_control", "5+3")
        try:
            parse_time_control(tc)
        except Exception:
            tc = "5+3"
        stake = float((data or {}).get("stake", 0) or 0)
        rated = bool((data or {}).get("rated", True))
        opponent_name = sanitize_text((data or {}).get("opponent", ""), 40)

        opponent = None
        if opponent_name:
            opponent = db.session.query(User).filter_by(
                username=opponent_name
            ).first()

        if stake > 0:
            wallet = db.session.query(User).get(current_user.id).wallet
            if wallet.balance < stake:
                socketio.emit("lobby:error",
                              {"msg": "Insufficient balance for stake."},
                              to=request.sid)
                return

        ch = Challenge(
            challenger_id=current_user.id,
            opponent_id=opponent.id if opponent else None,
            time_control=tc, stake=stake, rated=rated, status="open",
        )
        db.session.add(ch)
        db.session.commit()
        if stake > 0:
            try:
                lock_stake(current_user.id, stake, f"challenge_{ch.id}")
            except ValueError:
                db.session.delete(ch)
                db.session.commit()
                socketio.emit("lobby:error",
                              {"msg": "Insufficient balance to lock stake."},
                              to=request.sid)
                return
        _broadcast_challenges()
        if opponent:
            notes.notify(opponent.id, "challenge",
                         f"{current_user.username} challenged you!")

    @socketio.on("lobby:challenge_accept")
    def lobby_accept_challenge(data):
        """Accept an open challenge and start a game (with stake lock)."""
        if not current_user.is_authenticated:
            return
        ch_id = int((data or {}).get("challenge_id", 0))
        ch = db.session.get(Challenge, ch_id)
        if not ch or ch.status != "open":
            return
        if ch.opponent_id and ch.opponent_id != current_user.id:
            socketio.emit("lobby:error", {"msg": "Challenge is private."},
                          to=request.sid)
            return
        if ch.challenger_id == current_user.id:
            socketio.emit("lobby:error", {"msg": "Cannot accept own challenge."},
                          to=request.sid)
            return

        # Lock acceptor stake too (if any).
        if ch.stake > 0:
            try:
                lock_stake(current_user.id, ch.stake, f"challenge_{ch.id}")
            except ValueError:
                socketio.emit("lobby:error",
                              {"msg": "Insufficient balance to accept stake."},
                              to=request.sid)
                return

        # Build the game.
        import secrets
        room_id = "room_" + secrets.token_hex(6)
        tc = parse_time_control(ch.time_control)
        game = Game(
            room_id=room_id,
            white_id=ch.challenger_id,
            black_id=current_user.id,
            time_control=ch.time_control,
            increment_ms=tc.increment_ms,
            white_clock_ms=tc.base_ms,
            black_clock_ms=tc.base_ms,
            stake=ch.stake,
            pot=ch.stake * 2,
            rated=ch.rated,
            status="active",
            commission_rate=Settings.get(db.session).commission_rate,
            start_fen="startpos",
        )
        # Clock does NOT start on creation — both timers stay still until both
        # players have moved at least once (Black's first move starts White's clock).
        db.session.add(game)
        ch.status = "started"
        db.session.commit()

        # Notify both players to open the board.
        notes.notify(ch.challenger_id, "match_start",
                     f"Match vs {current_user.username} started.",
                     {"room_id": room_id})
        notes.notify(current_user.id, "match_start",
                     f"Match vs {ch.challenger.username} started.",
                     {"room_id": room_id})
        _broadcast_challenges()
        socketio.emit("game:start", {"room_id": room_id},
                      to=f"user_{ch.challenger_id}")
        socketio.emit("game:start", {"room_id": room_id},
                      to=f"user_{current_user.id}")

    @socketio.on("lobby:challenge_cancel")
    def lobby_cancel_challenge(data):
        ch_id = int((data or {}).get("challenge_id", 0))
        ch = db.session.get(Challenge, ch_id)
        if not ch:
            return
        if ch.challenger_id != current_user.id and not current_user.is_admin:
            return
        if ch.stake > 0:
            unlock_refund(ch.challenger_id, ch.stake, f"challenge_{ch.id}")
        ch.status = "cancelled"
        db.session.commit()
        _broadcast_challenges()

    @socketio.on("lobby:chat")
    def lobby_chat(data):
        body = sanitize_text((data or {}).get("body", ""), 1000)
        if not body:
            return
        msg = Message(sender_id=current_user.id, scope="lobby", body=body)
        db.session.add(msg)
        db.session.commit()
        socketio.emit("lobby:chat", {
            "username": current_user.username,
            "body": body,
            "avatar": current_user.avatar,
            "ts": msg.created_at.isoformat(),
        }, to="lobby")

    @socketio.on("lobby:typing")
    def lobby_typing(data):
        socketio.emit("lobby:typing", {
            "username": current_user.username,
        }, to="lobby", include_self=False)

    # ===================== GAME =====================
    @socketio.on("game:join")
    def game_join(data):
        room_id = (data or {}).get("room_id")
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game:
            return
        join_room(f"game:{room_id}")
        with state_lock:
            seats = game_sids.setdefault(room_id, {})
            if game.white_id == current_user.id:
                seats[game.white_id] = request.sid
            elif game.black_id == current_user.id:
                seats[game.black_id] = request.sid
            seen = game_last_seen.setdefault(room_id, {})
            seen[current_user.id] = time.time()
        # Send current state to the joiner.
        from zedchess.services.game_service import _state_payload
        socketio.emit("game:state", _state_payload(game), to=request.sid)
        _broadcast_clocks(room_id)

    @socketio.on("game:move")
    def game_move(data):
        room_id = (data or {}).get("room_id")
        san = sanitize_text((data or {}).get("san", ""), 10)
        index = int((data or {}).get("index", 0))
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game:
            return
        # Authorisation: must be your turn and correct order.
        try:
            verify_turn(game, current_user.id)
            verify_move_order(game, index)
        except Exception as e:
            socketio.emit("game:illegal", {"msg": str(e)}, to=request.sid)
            return
        # Accept either UCI ("e2e4", "e7e8q") or SAN; normalise to SAN.
        san = san.strip()
        if san and len(san) >= 4 and san[1] in "12345678" and san[3] in "12345678" \
           and san[0] in "abcdefgh" and san[2] in "abcdefgh":
            san = uci_to_san(game, san)
        try:
            state = apply_move(game, san, index)
        except ValueError as e:
            socketio.emit("game:illegal", {"msg": str(e)}, to=request.sid)
            return
        socketio.emit("game:state", state, to=f"game:{room_id}")
        # If game finished, notify + clean up.
        if state["status"] == "finished":
            _end_game_cleanup(room_id)

    @socketio.on("game:legal")
    def game_legal(data):
        """Return legal UCI target squares for a selected piece of the side to move."""
        room_id = (data or {}).get("room_id")
        from_sq = (data or {}).get("from")
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game or game.status != "active":
            return
        # Only the side to move may query legal moves.
        turn = game.turn_color()
        if (turn == "white" and game.white_id != current_user.id) or \
           (turn == "black" and game.black_id != current_user.id):
            return
        from zedchess.services.game_service import legal_targets
        targets = legal_targets(game, from_sq)
        socketio.emit("game:legal", {
            "room_id": room_id,
            "from": from_sq,
            "moves": targets,
        }, to=request.sid)

    @socketio.on("game:resign")
    def game_resign(data):
        room_id = (data or {}).get("room_id")
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game:
            return
        color = "white" if game.white_id == current_user.id else "black"
        state = resign_game(game, color)
        socketio.emit("game:state", state, to=f"game:{room_id}")
        _end_game_cleanup(room_id)

    @socketio.on("game:draw_offer")
    def game_draw_offer(data):
        """A player proposes a draw. The opponent must accept or decline."""
        room_id = (data or {}).get("room_id")
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game or game.status != "active":
            return
        if current_user.id not in (game.white_id, game.black_id):
            return
        # Only the side to move (or either side, like Lichess) may offer; we
        # allow either player to offer, but not twice in a row from the same
        # side without a response. Store the offerer on the game.
        from zedchess.services.game_service import _state_payload
        # Avoid duplicate offers stacking: clear any previous pending offer.
        game.pending_draw_from = current_user.id
        db.session.commit()
        opponent_id = game.black_id if current_user.id == game.white_id else game.white_id
        # Notify the opponent with an actionable prompt.
        socketio.emit("game:draw_offered", {
            "room_id": room_id,
            "from": current_user.id,
            "from_name": current_user.username,
        }, to=f"user_{opponent_id}")
        # Confirm to the offerer that the offer is pending.
        socketio.emit("game:draw_pending", {"room_id": room_id}, to=request.sid)

    @socketio.on("game:draw_respond")
    def game_draw_respond(data):
        """Opponent accepts or declines the pending draw offer."""
        room_id = (data or {}).get("room_id")
        accept = bool((data or {}).get("accept", False))
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game or game.status != "active":
            return
        if game.pending_draw_from is None:
            return
        # Only the *opponent* of the offerer may respond.
        if current_user.id == game.pending_draw_from:
            return
        if current_user.id not in (game.white_id, game.black_id):
            return
        offerer_id = game.pending_draw_from
        game.pending_draw_from = None
        if accept:
            state = agree_draw(game)
            socketio.emit("game:state", state, to=f"game:{room_id}")
            _end_game_cleanup(room_id)
        else:
            socketio.emit("game:draw_declined", {
                "room_id": room_id,
                "by_name": current_user.username,
            }, to=f"user_{offerer_id}")
            db.session.commit()

    @socketio.on("game:ping")
    def game_ping(data):
        """Client heartbeat; used for disconnect grace + clock integrity."""
        room_id = (data or {}).get("room_id")
        if not room_id:
            return
        game = db.session.query(Game).filter_by(room_id=room_id).first()
        if not game:
            return
        with state_lock:
            seen = game_last_seen.setdefault(room_id, {})
            if current_user.id in seen or current_user.id in (
                game.white_id, game.black_id
            ):
                seen[current_user.id] = time.time()

    @socketio.on("game:chat")
    def game_chat(data):
        room_id = (data or {}).get("room_id")
        body = sanitize_text((data or {}).get("body", ""), 1000)
        if not body or not room_id:
            return
        socketio.emit("game:chat", {
            "username": current_user.username, "body": body,
        }, to=f"game:{room_id}")

    @socketio.on("game:leave")
    def game_leave(data):
        room_id = (data or {}).get("room_id")
        _detach_from_games(request.sid, current_user.id, room_id)
        leave_room(f"game:{room_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def public_online() -> list:
    out = []
    for uid in list(online_users.keys()):
        u = db.session.get(User, uid)
        if u:
            out.append(u.to_public_dict())
    return out


def _broadcast_challenges():
    from zedchess.models import Challenge
    challenges = (
        db.session.query(Challenge)
        .filter(Challenge.status.in_(["open", "accepted"]))
        .order_by(Challenge.created_at.desc())
        .limit(50)
        .all()
    )
    payload = []
    for c in challenges:
        payload.append({
            "id": c.id,
            "challenger": c.challenger.username,
            "opponent": c.opponent.username if c.opponent else None,
            "time_control": c.time_control,
            "stake": c.stake,
            "rated": c.rated,
        })
    socketio.emit("lobby:challenges", payload, to="lobby")


def _broadcast_clocks(room_id: str):
    """Push the authoritative clock snapshot to everyone in the room.

    Both players receive identical banked values plus the server timestamp, so
    their clients interpolate in lock-step and stay in sync regardless of
    network jitter.
    """
    game = db.session.query(Game).filter_by(room_id=room_id).first()
    if not game:
        return
    from zedchess.services.clock_service import clock_payload
    socketio.emit("game:clock", clock_payload(game), to=f"game:{room_id}")


def _end_game_cleanup(room_id: str):
    with state_lock:
        game_sids.pop(room_id, None)
        game_last_seen.pop(room_id, None)


def _detach_from_games(sid: str, uid: int, only_room: str = None):
    with state_lock:
        rooms = [only_room] if only_room else list(game_sids.keys())
        for room_id in rooms:
            seats = game_sids.get(room_id)
            if seats and uid in seats and seats[uid] == sid:
                seats.pop(uid, None)
            seen = game_last_seen.get(room_id)
            if seen and uid in seen:
                seen.pop(uid, None)


# ---------------------------------------------------------------------------
# Clock ticker — single background thread, server-authoritative.
#
# The thread NEVER writes the clock on every tick. It only:
#   * reads the stored banked values + clock_started_at for active games,
#   * detects a flag-fall (active remaining <= 0) and ends the game,
#   * broadcasts the authoritative snapshot so both clients keep ticking.
# Live remaining time is derived on the client from wall-clock + server_time,
# so the display is smooth and accurate even if the ticker is briefly delayed.
# ---------------------------------------------------------------------------
TICK_INTERVAL = 0.2          # seconds between broadcasts (smoothness)
PERSIST_INTERVAL = 3.0       # seconds between banked-time DB writes
_last_persist = 0.0


def start_clock_ticker(socketio):
    """Spawn the clock thread (called from run.py)."""

    def tick():
        import sqlite3
        while True:
            time.sleep(TICK_INTERVAL)
            try:
                with state_lock:
                    rooms = list(game_sids.keys())
                for room_id in rooms:
                    _tick_room(room_id, socketio)
            except Exception:
                # A transient DB/lock blip must not kill the ticker.
                continue

    t = threading.Thread(target=tick, daemon=True)
    t.start()
    return t


def _tick_room(room_id: str, socketio):
    game = db.session.query(Game).filter_by(room_id=room_id).first()
    if not game or game.status != "active":
        return

    from zedchess.services.clock_service import (
        live_clocks, bank_active_clock, has_flag_fallen, now_seconds,
        clock_payload, is_clock_running,
    )

    # Before both players have moved, the clock is frozen — just broadcast the
    # (static) snapshot so both clients show full, still timers, and bail out.
    if not is_clock_running(game):
        socketio.emit("game:clock", clock_payload(game), to=f"game:{room_id}")
        return

    now = now_seconds()
    turn = game.turn_color()

    # ---- Disconnect grace: if the active player has been silent past the
    #      grace window, their flag is effectively fallen -> loss on time. ----
    settings = Settings.get(db.session)
    grace = settings.disconnect_forfeit_seconds
    with state_lock:
        seen = game_last_seen.get(room_id, {})
    mover_id = game.white_id if turn == "white" else game.black_id
    last = seen.get(mover_id)
    if last is not None and (now - last) > grace and has_flag_fallen(game, now):
        state = timeout_for(game, turn)
        socketio.emit("game:state", state, to=f"game:{room_id}")
        _end_game_cleanup(room_id)
        return

    # ---- Timeout detection (authoritative). ----
    if has_flag_fallen(game, now):
        state = timeout_for(game, turn)
        socketio.emit("game:state", state, to=f"game:{room_id}")
        _end_game_cleanup(room_id)
        return

    # ---- Periodic persistence of banked time so a server restart / refresh
    #      never loses more than a few seconds. ----
    global _last_persist
    if now - _last_persist >= PERSIST_INTERVAL:
        bank_active_clock(game, now)
        try:
            db.session.commit()
            _last_persist = now
        except Exception:
            db.session.rollback()

    # ---- Broadcast the authoritative snapshot to both players. ----
    socketio.emit("game:clock", clock_payload(game), to=f"game:{room_id}")