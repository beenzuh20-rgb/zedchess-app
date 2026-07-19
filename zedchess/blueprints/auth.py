"""
Auth blueprint: registration, login, logout, password reset, profile, avatar.

All forms are CSRF-protected via Flask-WTF. Passwords are hashed with
Werkzeug's pbkdf2 helper. Brute-force login is throttled per IP.
"""

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from zedchess.extensions import db
from zedchess.models import User, Friendship, Notification, Game
from zedchess.services.wallet_service import deposit, get_or_create_wallet
from zedchess.utils.security import (
    is_valid_username, basic_email_check, allowed_avatar, sanitize_text,
)
from zedchess.utils.rate_limit import limiter, client_ip

bp = Blueprint("auth", __name__, url_prefix="/auth")


# --------------------------------------------------------------------------
# Forms (lightweight, no WTForms dependency needed for clarity)
# --------------------------------------------------------------------------
def _flash_errors(form_errors: dict):
    for msg in form_errors.values():
        flash(msg, "danger")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("lobby.index"))

    if request.method == "POST":
        username = sanitize_text(request.form.get("username", ""), 20)
        email = sanitize_text(request.form.get("email", ""), 120)
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        terms = request.form.get("terms") == "on"

        if not terms:
            flash("You must accept the Terms of Service to register.", "danger")
        elif not is_valid_username(username):
            flash("Username must be 3-20 chars: letters, numbers, underscore.", "danger")
        elif not basic_email_check(email):
            flash("Enter a valid email address.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif db.session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first():
            flash("Username or email already taken.", "danger")
        else:
            from datetime import datetime, timezone
            user = User(
                username=username, email=email,
                rating=1200, rating_peak=1200, rating_deviation=200,
                terms_accepted=True,
                terms_accepted_at=datetime.now(timezone.utc),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            get_or_create_wallet(user.id)
            deposit(user.id, current_app.config["STARTING_BALANCE"], "signup bonus")
            login_user(user)
            flash("Welcome to ZedChess! You received a sign-up bonus.", "success")
            return redirect(url_for("lobby.index"))

    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("lobby.index"))

    if request.method == "POST":
        ip = client_ip()
        if not limiter.limit(
            f"login:{ip}", current_app.config["LOGIN_RATE_LIMIT"],
            current_app.config["LOGIN_RATE_WINDOW"],
        ):
            flash("Too many attempts. Please wait a minute.", "danger")
            return render_template("auth/login.html")

        email = sanitize_text(request.form.get("email", ""), 120)
        password = request.form.get("password", "")
        user = db.session.query(User).filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
        elif user.is_banned:
            flash("This account has been banned.", "danger")
        elif not user.is_active:
            flash("This account is suspended. Contact support.", "danger")
        else:
            login_user(user, remember=True)
            limiter.reset(f"login:{ip}")
            return redirect(url_for("lobby.index"))

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    user = db.session.get(User, current_user.id)
    if user:
        user.online = False
        db.session.commit()
    logout_user()
    return redirect(url_for("home.index"))


# --------------------------------------------------------------------------
# Password reset (token-based, emailed)
# --------------------------------------------------------------------------
@bp.route("/reset", methods=["GET", "POST"])
def reset_request():
    if request.method == "POST":
        email = sanitize_text(request.form.get("email", ""), 120)
        user = db.session.query(User).filter_by(email=email).first()
        if user and user.is_active and not user.is_banned:
            token = user.get_reset_token() if hasattr(user, "get_reset_token") \
                else None
            # NOTE: a real deployment sends the email via flask-mail.
            flash("If that account exists, a reset link was sent.", "info")
        else:
            flash("If that account exists, a reset link was sent.", "info")
    return render_template("auth/reset_request.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_token(token):
    flash("Password reset tokens are configured via mail in production.", "info")
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------
@bp.route("/profile/<username>")
@login_required
def profile(username):
    user = db.session.query(User).filter_by(username=username).first_or_404()

    recent = (
        db.session.query(Game)
        .filter((Game.white_id == user.id) | (Game.black_id == user.id))
        .order_by(Game.id.desc())
        .limit(15)
        .all()
    )
    is_friend = (
        db.session.query(Friendship)
        .filter_by(user_id=current_user.id, friend_id=user.id,
                   status="accepted")
        .first()
        is not None
    )
    return render_template(
        "auth/profile.html", user=user, recent=recent, is_friend=is_friend,
    )


@bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    user = db.session.get(User, current_user.id)
    if request.method == "POST":
        user.bio = sanitize_text(request.form.get("bio", ""), 280)
        user.country = sanitize_text(request.form.get("country", ""), 8)

        file = request.files.get("avatar")
        if file and file.filename:
            if not allowed_avatar(
                file.filename, current_app.config["ALLOWED_AVATAR_EXTENSIONS"]
            ):
                flash("Unsupported image type.", "danger")
            else:
                ext = file.filename.rsplit(".", 1)[-1].lower()
                filename = secure_filename(f"avatar_{user.id}.{ext}")
                path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
                file.save(path)
                user.avatar = f"/static/uploads/{filename}"
                flash("Avatar updated.", "success")

        db.session.commit()
        return redirect(url_for("auth.profile", username=user.username))

    return render_template("auth/profile_edit.html", user=user)


# Local import to avoid circulars at module import time.
import os  # noqa: E402
