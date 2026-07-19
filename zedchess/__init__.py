"""
Flask application factory for ZedChess.

``create_app`` builds the Flask + SocketIO app, binds extensions, registers
blueprints and SocketIO handlers, and ensures an admin account + default
settings exist. Importing this module must NOT trigger side effects that
require a configured app, so model/socket registration happens inside the
factory.
"""

import os

from zedchess.extensions import (
    db, login_manager, migrate, csrf, mail, socketio,
)
from zedchess.config import get_config


def create_app(config_name: str = None) -> object:
    from flask import Flask

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(get_config(config_name))

    # Ensure upload directory exists.
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Bind extensions to the app.
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        ping_timeout=app.config["SOCKETIO_PING_TIMEOUT"],
        ping_interval=app.config["SOCKETIO_PING_INTERVAL"],
        async_mode=app.config["SOCKETIO_ASYNC_MODE"],
    )

    # Expose csrf token to all templates (used by forms + fetch).
    @app.context_processor
    def inject_csrf():
        from flask_wtf.csrf import generate_csrf
        return dict(csrf_token=generate_csrf)

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        return dict(app_name="ZedChess", now=datetime.now())

    # Error handlers.
    register_error_handlers(app)

    # Blueprints.
    from zedchess.blueprints import (
        auth, wallet, lobby, game, home, admin, legal,
    )
    app.register_blueprint(home.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(wallet.bp)
    app.register_blueprint(lobby.bp)
    app.register_blueprint(game.bp)
    app.register_blueprint(legal.bp)
    app.register_blueprint(admin.bp)

    # Socket handlers.
    from zedchess.sockets import register_socket_handlers
    register_socket_handlers(socketio)

    # First-run setup: tables + admin + default settings.
    with app.app_context():
        db.create_all()
        # Idempotently add columns introduced after the initial schema so an
        # existing database stays compatible without a full migration run.
        _ensure_columns(db)
        from zedchess.models import User, Settings
        Settings.get(db.session)
        _ensure_admin(app)

    return app


def _ensure_columns(db) -> None:
    """Add any columns added after initial release to an existing DB (idempotent)."""
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(db.engine)
    if "games" not in inspector.get_table_names():
        return

    # games table
    existing_games = {c["name"] for c in inspector.get_columns("games")}
    wanted_games = {
        "pending_draw_from": "INTEGER",
    }
    with db.engine.begin() as conn:
        for col, coltype in wanted_games.items():
            if col not in existing_games:
                conn.execute(text(f"ALTER TABLE games ADD COLUMN {col} {coltype}"))

    # users table (consent tracking)
    if "users" in inspector.get_table_names():
        existing_users = {c["name"] for c in inspector.get_columns("users")}
        wanted_users = {
            "terms_accepted": "BOOLEAN NOT NULL DEFAULT 0",
            "terms_accepted_at": "TIMESTAMP",
        }
        with db.engine.begin() as conn:
            for col, coltype in wanted_users.items():
                if col not in existing_users:
                    conn.execute(
                        text(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
                    )


def _ensure_admin(app) -> None:
    from zedchess.models import User

    username = app.config["ADMIN_USERNAME"]
    if not db.session.query(User).filter_by(username=username).first():
        admin = User(
            username=username,
            email=app.config["ADMIN_EMAIL"],
            is_admin=True,
            rating=1200,
            rating_peak=1200,
        )
        admin.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()
        # Give admin a wallet.
        from zedchess.services.wallet_service import get_or_create_wallet
        get_or_create_wallet(admin.id)


def register_error_handlers(app) -> None:
    from flask import render_template

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500
