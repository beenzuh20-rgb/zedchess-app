"""
SQLAlchemy ORM models for ZedChess.

Design notes
------------
* Every monetary value is stored as ``Float`` with explicit sign tracking in
  the ``Transaction`` ledger so the wallet balance is always derivable and
  auditable (no reliance on a single mutable ``balance`` column).
* Game results drive the Elo system; ``RatingHistory`` keeps a per-user
  timeline for the rating graph.
* The ``Settings`` singleton stores platform-wide values (commission, default
  timers, forced-forfeit window) editable from the admin panel.
"""

from datetime import datetime, timezone

from werkzeug.security import generate_password_hash, check_password_hash

from zedchess.extensions import db, login_manager
from flask_login import UserMixin


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    """A platform account. Also serves as the Flask-Login identity."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Profile
    avatar = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.String(280), nullable=True)
    country = db.Column(db.String(8), nullable=True)

    # Ratings (Elo). ``rating`` is current, ``rating_peak`` is highest reached.
    rating = db.Column(db.Float, default=1200.0, nullable=False)
    rating_peak = db.Column(db.Float, default=1200.0, nullable=False)
    rating_deviation = db.Column(db.Float, default=200.0, nullable=False)

    # Stats
    wins = db.Column(db.Integer, default=0, nullable=False)
    losses = db.Column(db.Integer, default=0, nullable=False)
    draws = db.Column(db.Integer, default=0, nullable=False)
    games_played = db.Column(db.Integer, default=0, nullable=False)

    # Status / moderation
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)   # suspend
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    online = db.Column(db.Boolean, default=False, nullable=False)
    last_seen = db.Column(db.DateTime, default=_utcnow)

    # Consent
    terms_accepted = db.Column(db.Boolean, default=False, nullable=False)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    # Relationships
    wallet = db.relationship(
        "Wallet", back_populates="owner", uselist=False,
        cascade="all, delete-orphan",
    )
    games_white = db.relationship(
        "Game", back_populates="white_player",
        foreign_keys="Game.white_id", lazy="dynamic",
    )
    games_black = db.relationship(
        "Game", back_populates="black_player",
        foreign_keys="Game.black_id", lazy="dynamic",
    )

    # ---- auth helpers ----------------------------------------------------
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def balance(self) -> float:
        return self.wallet.balance if self.wallet else 0.0

    @property
    def locked(self) -> float:
        return self.wallet.locked if self.wallet else 0.0

    @property
    def display_name(self) -> str:
        return self.username

    def to_public_dict(self) -> dict:
        """Lightweight, safe representation for the client/lobby."""
        return {
            "id": self.id,
            "username": self.username,
            "avatar": self.avatar,
            "rating": int(self.rating),
            "online": self.online,
            "is_admin": self.is_admin,
        }


# ---------------------------------------------------------------------------
# Wallet + ledger
# ---------------------------------------------------------------------------
class Wallet(db.Model):
    """A user's balance. ``balance`` is spendable, ``locked`` is in active pots."""

    __tablename__ = "wallets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    balance = db.Column(db.Float, default=0.0, nullable=False)
    locked = db.Column(db.Float, default=0.0, nullable=False)  # money in pots
    total_earned = db.Column(db.Float, default=0.0, nullable=False)

    owner = db.relationship("User", back_populates="wallet")
    transactions = db.relationship(
        "Transaction", back_populates="wallet", lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="Transaction.created_at.desc()",
    )

    @property
    def available(self) -> float:
        return max(self.balance, 0.0)


class Transaction(db.Model):
    """Immutable ledger of every wallet movement."""

    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(
        db.Integer, db.ForeignKey("wallets.id"), nullable=False, index=True
    )
    # amount sign: positive = credit, negative = debit
    amount = db.Column(db.Float, nullable=False)
    kind = db.Column(db.String(32), nullable=False)  # deposit, withdraw, stake,
    #                                                    payout, refund, adjust
    status = db.Column(db.String(16), default="completed", nullable=False)
    # pending | completed | rejected  (withdrawals start as pending)
    reference = db.Column(db.String(64), nullable=True)  # game id / note
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    wallet = db.relationship("Wallet", back_populates="transactions")


# ---------------------------------------------------------------------------
# Challenges (lobby)
# ---------------------------------------------------------------------------
class Challenge(db.Model):
    """An open challenge in the lobby (excludes live games)."""

    __tablename__ = "challenges"

    id = db.Column(db.Integer, primary_key=True)
    challenger_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    opponent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    # NULL opponent == open challenge (anyone can accept)

    time_control = db.Column(db.String(16), nullable=False)  # e.g. "5+3"
    stake = db.Column(db.Float, default=0.0, nullable=False)
    rated = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(16), default="open", nullable=False)
    # open | accepted | cancelled | started
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    challenger = db.relationship("User", foreign_keys=[challenger_id])
    opponent = db.relationship("User", foreign_keys=[opponent_id])


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------
class Game(db.Model):
    """A played game. Source of truth for results, Elo and payouts."""

    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(32), unique=True, nullable=False, index=True)

    white_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    black_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Chess state
    moves = db.Column(db.Text, default="", nullable=False)  # SAN, space separated
    pgn = db.Column(db.Text, nullable=True)
    fen = db.Column(db.String(120), nullable=True)
    start_fen = db.Column(db.String(120), default="startpos", nullable=False)

    # Time control + clocks (server-authoritative, milliseconds)
    time_control = db.Column(db.String(16), default="5+3", nullable=False)
    increment_ms = db.Column(db.Integer, default=3000, nullable=False)
    white_clock_ms = db.Column(db.Integer, default=300000, nullable=False)
    black_clock_ms = db.Column(db.Integer, default=300000, nullable=False)
    clock_started_at = db.Column(db.Float, nullable=True)  # epoch seconds

    # Stake / betting
    stake = db.Column(db.Float, default=0.0, nullable=False)
    pot = db.Column(db.Float, default=0.0, nullable=False)
    commission_rate = db.Column(db.Float, default=0.05, nullable=False)
    payout_done = db.Column(db.Boolean, default=False, nullable=False)
    rated = db.Column(db.Boolean, default=True, nullable=False)

    # Result
    status = db.Column(db.String(16), default="waiting", nullable=False)
    # waiting | active | finished | aborted
    result = db.Column(db.String(16), nullable=True)  # white | black | draw
    termination = db.Column(db.String(32), nullable=True)
    # checkmate | timeout | resignation | disconnect | draw_agreed |
    #           threefold | stalemate | insufficient | fifty_move | abort

    # Pending draw offer: user id of the player who proposed the draw (None if none).
    pending_draw_from = db.Column(db.Integer, nullable=True)

    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)

    white_player = db.relationship("User", foreign_keys=[white_id])
    black_player = db.relationship("User", foreign_keys=[black_id])

    def turn_color(self) -> str:
        """Whose turn, derived from move parity (white always moves first)."""
        n = len(self.moves.split()) if self.moves else 0
        return "white" if n % 2 == 0 else "black"

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "white_id": self.white_id,
            "black_id": self.black_id,
            "moves": self.moves.split() if self.moves else [],
            "fen": self.fen,
            "time_control": self.time_control,
            "white_clock_ms": self.white_clock_ms,
            "black_clock_ms": self.black_clock_ms,
            "turn": self.turn_color(),
            "stake": self.stake,
            "rated": self.rated,
            "status": self.status,
            "result": self.result,
            "termination": self.termination,
        }


# ---------------------------------------------------------------------------
# Rating history (for the rating graph)
# ---------------------------------------------------------------------------
class RatingHistory(db.Model):
    """Append-only per-user rating timeline."""

    __tablename__ = "rating_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    rating = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Social: friends + blocks
# ---------------------------------------------------------------------------
class Friendship(db.Model):
    """Friend / block relation between two users (direction-aware)."""

    __tablename__ = "friendships"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    friend_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    status = db.Column(db.String(16), default="pending", nullable=False)
    # pending | accepted | blocked
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "friend_id", name="uq_friendship"),
    )


# ---------------------------------------------------------------------------
# Chat + private messages
# ---------------------------------------------------------------------------
class Message(db.Model):
    """Lobby / game / private chat message."""

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # Scope: room="" lobby, room="game:<room_id>", or "pm:<user_id>"
    scope = db.Column(db.String(64), default="lobby", nullable=False, index=True)
    body = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    sender = db.relationship("User")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class Notification(db.Model):
    """Real-time + persisted user notifications."""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    type = db.Column(db.String(32), nullable=False)
    body = db.Column(db.String(280), nullable=False)
    data = db.Column(db.Text, nullable=True)  # JSON payload
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Platform settings (admin-editable singleton)
# ---------------------------------------------------------------------------
class Settings(db.Model):
    """Singleton holding platform-wide tunables."""

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    commission_rate = db.Column(db.Float, default=0.05, nullable=False)
    disconnect_forfeit_seconds = db.Column(db.Integer, default=30, nullable=False)
    default_time_control = db.Column(db.String(16), default="5+3", nullable=False)
    maintenance_mode = db.Column(db.Boolean, default=False, nullable=False)
    announcement = db.Column(db.Text, nullable=True)

    @staticmethod
    def get(db_session):
        """Return the singleton row, creating it if missing."""
        s = db_session.query(Settings).first()
        if not s:
            s = Settings()
            db_session.add(s)
            db_session.commit()
        return s
