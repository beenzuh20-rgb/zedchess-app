"""
Admin blueprint.

Restricted to ``is_admin`` users. Covers user moderation, balance edits,
withdrawal approvals, configuration of commission + timers, and stats.
"""

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
)
from flask_login import login_required, current_user

from zedchess.extensions import db
from zedchess.models import User, Game, Transaction, Settings, Challenge
from zedchess.services.wallet_service import (
    approve_withdrawal, reject_withdrawal, adjust_balance,
)
from zedchess.utils.security import sanitize_text

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*a, **k):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("home.index"))
        return func(*a, **k)

    return wrapper


@bp.route("/")
@login_required
@admin_required
def dashboard():
    users = db.session.query(User).count()
    active = db.session.query(Game).filter_by(status="active").count()
    finished = db.session.query(Game).filter_by(status="finished").count()
    pending = db.session.query(Transaction).filter_by(status="pending").count()
    settings = Settings.get(db.session)
    return render_template(
        "admin/dashboard.html",
        stats={"users": users, "active": active, "finished": finished,
               "pending": pending},
        settings=settings,
    )


@bp.route("/users")
@login_required
@admin_required
def users():
    q = sanitize_text(request.args.get("q", ""), 40)
    query = db.session.query(User)
    if q:
        query = query.filter(User.username.ilike(f"%{q}%"))
    users = query.order_by(User.id.desc()).limit(200).all()
    return render_template("admin/users.html", users=users, q=q)


@bp.route("/users/<int:user_id>/suspend", methods=["POST"])
@login_required
@admin_required
def suspend(user_id):
    user = db.session.get(User, user_id)
    if user and not user.is_admin:
        user.is_active = not user.is_active
        db.session.commit()
        flash(f"{user.username} {'unsuspended' if user.is_active else 'suspended'}.",
              "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/ban", methods=["POST"])
@login_required
@admin_required
def ban(user_id):
    user = db.session.get(User, user_id)
    if user and not user.is_admin:
        user.is_banned = not user.is_banned
        user.is_active = not user.is_banned
        db.session.commit()
        flash(f"{user.username} {'unbanned' if not user.is_banned else 'banned'}.",
              "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/adjust", methods=["POST"])
@login_required
@admin_required
def adjust(user_id):
    try:
        delta = float(request.form.get("delta", "0"))
    except ValueError:
        delta = 0
    if delta:
        adjust_balance(user_id, delta, "admin adjustment")
        flash("Balance adjusted.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/withdrawals")
@login_required
@admin_required
def withdrawals():
    pending = (
        db.session.query(Transaction)
        .filter_by(status="pending")
        .order_by(Transaction.created_at.desc())
        .all()
    )
    return render_template("admin/withdrawals.html", pending=pending)


@bp.route("/withdrawals/<int:tx_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_withdrawal_route(tx_id):
    approve_withdrawal(tx_id)
    flash("Withdrawal approved.", "success")
    return redirect(url_for("admin.withdrawals"))


@bp.route("/withdrawals/<int:tx_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_withdrawal_route(tx_id):
    tx = db.session.get(Transaction, tx_id)
    if tx:
        reject_withdrawal(tx_id, tx.wallet.user_id, -tx.amount)
        flash("Withdrawal rejected and refunded.", "info")
    return redirect(url_for("admin.withdrawals"))


@bp.route("/games")
@login_required
@admin_required
def games():
    status = request.args.get("status", "active")
    games = (
        db.session.query(Game)
        .filter_by(status=status)
        .order_by(Game.id.desc())
        .limit(100)
        .all()
    )
    return render_template("admin/games.html", games=games, status=status)


@bp.route("/config", methods=["GET", "POST"])
@login_required
@admin_required
def config():
    settings = Settings.get(db.session)
    if request.method == "POST":
        settings.commission_rate = float(
            request.form.get("commission_rate", settings.commission_rate)
        )
        settings.disconnect_forfeit_seconds = int(
            request.form.get("disconnect_seconds",
                             settings.disconnect_forfeit_seconds)
        )
        settings.default_time_control = request.form.get(
            "default_time_control", settings.default_time_control
        )
        settings.announcement = sanitize_text(
            request.form.get("announcement", ""), 500
        )
        settings.maintenance_mode = request.form.get("maintenance") == "on"
        db.session.commit()
        flash("Settings saved.", "success")
    return render_template("admin/config.html", settings=settings)
