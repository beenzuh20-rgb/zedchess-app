"""
Game blueprint.

Serves the chess board page (live game), the "watch" page for spectators, and
a replay page built from stored PGN/FEN. Matchmaking challenge creation is
exposed here as a REST endpoint the lobby uses; the live move/clocks flow
through SocketIO.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from zedchess.extensions import db
from zedchess.models import Game, Challenge, User, Settings
from zedchess.services.wallet_service import get_or_create_wallet
from zedchess.utils.time_controls import (
    parse_time_control, is_legal_custom_time_control, TIME_CONTROL_PRESETS,
)
from zedchess.utils.rate_limit import limiter, client_ip

bp = Blueprint("game", __name__, url_prefix="/game")


@bp.route("/<room_id>")
@login_required
def board(room_id):
    game = db.session.query(Game).filter_by(room_id=room_id).first_or_404()
    return render_template("game/board.html", game=game, room_id=room_id)


@bp.route("/watch/<room_id>")
@login_required
def watch(room_id):
    game = db.session.query(Game).filter_by(room_id=room_id).first_or_404()
    return render_template("game/watch.html", game=game, room_id=room_id)


@bp.route("/replay/<room_id>")
@login_required
def replay(room_id):
    game = db.session.query(Game).filter_by(room_id=room_id).first_or_404()
    return render_template("game/replay.html", game=game, room_id=room_id)


# --------------------------------------------------------------------------
# Create a challenge (open / private / by username)
# --------------------------------------------------------------------------
@bp.route("/challenge", methods=["POST"])
@login_required
def create_challenge():
    ip = client_ip()
    if not limiter.limit(f"challenge:{ip}", 20, 60):
        flash("Slow down — too many challenges.", "danger")
        return redirect(url_for("lobby.index"))

    tc_spec = request.form.get("time_control", "5+3")
    try:
        parse_time_control(tc_spec)
    except Exception:
        tc_spec = "5+3"

    stake = float(request.form.get("stake", 0) or 0)
    rated = request.form.get("rated", "on") == "on"

    # Validate stake against balance.
    wallet = get_or_create_wallet(current_user.id)
    if stake > 0 and wallet.balance < stake:
        flash("Insufficient balance for that stake.", "danger")
        return redirect(url_for("lobby.index"))

    target_username = request.form.get("opponent")
    opponent = None
    if target_username:
        opponent = db.session.query(User).filter_by(
            username=target_username
        ).first()
        if not opponent or opponent.id == current_user.id:
            flash("Invalid opponent.", "danger")
            return redirect(url_for("lobby.index"))

    challenge = Challenge(
        challenger_id=current_user.id,
        opponent_id=opponent.id if opponent else None,
        time_control=tc_spec,
        stake=stake,
        rated=rated,
        status="open",
    )
    db.session.add(challenge)
    db.session.commit()

    # Lock the challenger's stake now (refunded if unmet / aborted).
    if stake > 0:
        from zedchess.services.wallet_service import lock_stake
        try:
            lock_stake(current_user.id, stake, f"challenge_{challenge.id}")
        except ValueError:
            db.session.delete(challenge)
            db.session.commit()
            flash("Insufficient balance to lock the stake.", "danger")
            return redirect(url_for("lobby.index"))

    return redirect(url_for("lobby.index"))
