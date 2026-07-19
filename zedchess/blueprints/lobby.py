"""
Lobby blueprint.

Serves the real-time lobby page (challenge list, online users, search,
friends, chat). Real-time behaviour is handled by the SocketIO handlers in
``zedchess.sockets``; this blueprint only renders the page and friend/PM
REST endpoints.
"""

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
)
from flask_login import login_required, current_user

from zedchess.extensions import db
from zedchess.models import User, Friendship, Challenge, Settings
from zedchess.utils.security import sanitize_text

bp = Blueprint("lobby", __name__, url_prefix="/lobby")


@bp.route("/")
@login_required
def index():
    settings = Settings.get(db.session)
    challenges = (
        db.session.query(Challenge)
        .filter(Challenge.status.in_(["open", "accepted"]))
        .order_by(Challenge.created_at.desc())
        .limit(50)
        .all()
    )
    # Mark user online while in the lobby.
    user = db.session.get(User, current_user.id)
    user.online = True
    from datetime import datetime, timezone
    user.last_seen = datetime.now(timezone.utc)
    db.session.commit()

    return render_template(
        "lobby/index.html",
        challenges=challenges,
        stake_presets=settings_default_stakes(),
        announcement=settings.announcement,
    )


def settings_default_stakes():
    from zedchess.config import get_config
    return get_config().STAKE_PRESETS


# --------------------------------------------------------------------------
# Friends
# --------------------------------------------------------------------------
@bp.route("/friends/add/<int:user_id>", methods=["POST"])
@login_required
def add_friend(user_id):
    if user_id == current_user.id:
        flash("You cannot friend yourself.", "danger")
        return redirect(url_for("lobby.index"))
    exists = db.session.query(Friendship).filter_by(
        user_id=current_user.id, friend_id=user_id
    ).first()
    if not exists:
        db.session.add(Friendship(
            user_id=current_user.id, friend_id=user_id, status="pending"
        ))
        db.session.commit()
    return redirect(request.referrer or url_for("lobby.index"))


@bp.route("/friends/accept/<int:user_id>", methods=["POST"])
@login_required
def accept_friend(user_id):
    fr = db.session.query(Friendship).filter_by(
        user_id=user_id, friend_id=current_user.id, status="pending"
    ).first()
    if fr:
        fr.status = "accepted"
        # Symmetric acceptance.
        db.session.add(Friendship(
            user_id=current_user.id, friend_id=user_id, status="accepted"
        ))
        db.session.commit()
    return redirect(request.referrer or url_for("lobby.index"))


@bp.route("/friends/block/<int:user_id>", methods=["POST"])
@login_required
def block_user(user_id):
    db.session.query(Friendship).filter_by(
        user_id=current_user.id, friend_id=user_id
    ).delete()
    db.session.add(Friendship(
        user_id=current_user.id, friend_id=user_id, status="blocked"
    ))
    db.session.commit()
    return redirect(request.referrer or url_for("lobby.index"))


# --------------------------------------------------------------------------
# Search players
# --------------------------------------------------------------------------
@bp.route("/search")
@login_required
def search():
    q = sanitize_text(request.args.get("q", ""), 40)
    results = []
    if q:
        results = (
            db.session.query(User)
            .filter(User.username.ilike(f"%{q}%"))
            .filter(User.is_banned.is_(False))
            .limit(20)
            .all()
        )
    return render_template("lobby/search.html", results=results, q=q)
