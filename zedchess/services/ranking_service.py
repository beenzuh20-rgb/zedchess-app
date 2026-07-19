"""
Ranking / leaderboard service.

Provides global, weekly and monthly leaderboards plus the per-user rating
graph data. Time windows are computed in UTC so they are deterministic across
server locales.
"""

from datetime import datetime, timedelta, timezone

from zedchess.extensions import db
from zedchess.models import User, RatingHistory


def _since(window: str) -> datetime:
    now = datetime.now(timezone.utc)
    if window == "weekly":
        return now - timedelta(days=7)
    if window == "monthly":
        return now - timedelta(days=30)
    return datetime.min.replace(tzinfo=timezone.utc)


def leaderboard(window: str = "global", limit: int = 50):
    """Return ranked users. ``window`` in {global, weekly, monthly}.

    For weekly/monthly we rank by the rating gained since the window start,
    which rewards recent performance (computed from ``RatingHistory``).
    """
    if window == "global":
        return (
            db.session.query(User)
            .filter(User.is_banned.is_(False))
            .order_by(User.rating.desc())
            .limit(limit)
            .all()
        )

    since = _since(window)
    # Users with positive rating change in the window.
    rows = (
        db.session.query(User)
        .join(RatingHistory, RatingHistory.user_id == User.id)
        .filter(RatingHistory.created_at >= since)
        .filter(User.is_banned.is_(False))
        .all()
    )
    # Approximate gain by latest history rating minus rating at window start.
    ranked = []
    for u in rows:
        hist = (
            db.session.query(RatingHistory)
            .filter(RatingHistory.user_id == u.id)
            .order_by(RatingHistory.created_at.asc())
            .all()
        )
        start = next((h.rating for h in hist if h.created_at >= since), u.rating)
        gain = u.rating - start
        ranked.append((u, gain))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return [u for u, _ in ranked[:limit]]


def rating_graph(user_id: int, days: int = 60) -> list[dict]:
    """Return [{t, rating}] points for the user's rating over time."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    points = (
        db.session.query(RatingHistory)
        .filter(RatingHistory.user_id == user_id)
        .filter(RatingHistory.created_at >= since)
        .order_by(RatingHistory.created_at.asc())
        .all()
    )
    return [
        {"t": p.created_at.isoformat(), "rating": p.rating} for p in points
    ]
