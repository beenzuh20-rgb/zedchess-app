"""
Application configuration.

Two primary environments are provided:

* ``DevelopmentConfig``  -> SQLite (default for local development)
* ``ProductionConfig``   -> PostgreSQL (set ``DATABASE_URL`` to migrate later)

PostgreSQL migration is a matter of switching ``DATABASE_URL`` and running the
migration scripts; no model changes are required thanks to SQLAlchemy's
dialect abstraction.
"""

import os
from datetime import timedelta


class Config:
    """Base configuration shared by every environment."""

    # ---- Core -------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-prod")
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # SQLite for development; override with a DATABASE_URL for PostgreSQL.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "zedchess.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # ---- Security ---------------------------------------------------------
    # Flask-WTF / CSRF protection for all POST forms.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    SESSION_COOKIE_SECURE = False          # enable (True) behind HTTPS in prod
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Brute-force protection: max login attempts per IP within window.
    LOGIN_RATE_LIMIT = 10
    LOGIN_RATE_WINDOW = 60  # seconds

    # ---- Uploads ----------------------------------------------------------
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024    # 4 MB max upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "zedchess", "static", "uploads")
    ALLOWED_AVATAR_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

    # ---- Mail (password reset) -------------------------------------------
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 25))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@zedchess.app")

    # ---- Gameplay ---------------------------------------------------------
    # Platform commission taken from every betting pot (0.05 = 5%).
    DEFAULT_COMMISSION_RATE = 0.05
    # Available quick-stake buttons (in "K" units: K5 == 5.0 coins).
    STAKE_PRESETS = [5, 10, 20, 50, 100]
    STARTING_BALANCE = 1000.0
    # Forfeit a game if a player stays disconnected past this many seconds.
    DISCONNECT_FORFEIT_SECONDS = 30
    # Generous grace period before a disconnect counts against the player.
    DISCONNECT_GRACE_SECONDS = 10

    # ---- SocketIO ---------------------------------------------------------
    SOCKETIO_PING_TIMEOUT = 20
    SOCKETIO_PING_INTERVAL = 10
    SOCKETIO_ASYNC_MODE = "threading"

    # ---- Admin ------------------------------------------------------------
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@zedchess.app")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


class DevelopmentConfig(Config):
    """Local development: verbose, SQLite, debug tooling on."""

    DEBUG = True
    ENV = "development"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production: conservative cookies, PostgreSQL via DATABASE_URL."""

    DEBUG = False
    ENV = "production"
    SESSION_COOKIE_SECURE = True
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(name: str = None) -> Config:
    """Resolve a configuration class from an environment name."""
    name = (name or os.environ.get("FLASK_ENV", "default")).lower()
    return CONFIG_MAP.get(name, DevelopmentConfig)
