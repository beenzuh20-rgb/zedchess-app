"""
Elo rating service.

Implements the standard Elo update used by chess platforms, with a K-factor
that scales by the lower-rated player's provisional status. Draws split the
point (0.5 each). All mutations are transactional and recorded in
``RatingHistory`` for the rating graph.
"""

from zedchess.extensions import db
from zedchess.models import User, RatingHistory

# K-factors
K_PROVISIONAL = 40  # rating_deviation high or few games
K_STANDARD = 20
K_STABLE = 10       # very established players


def _expected(a: float, b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((b - a) / 400.0))


def _k_factor(user: User) -> int:
    if user.games_played < 30 or user.rating_deviation > 100:
        return K_PROVISIONAL
    if user.rating >= 2000:
        return K_STABLE
    return K_STANDARD


def update_ratings(winner: User, loser: User) -> tuple[float, float]:
    """Apply a decisive result and return ``(new_winner, new_loser)`` ratings."""
    return _apply(winner, loser, score_winner=1.0)


def update_draw(a: User, b: User) -> tuple[float, float]:
    """Apply a drawn result to both players."""
    return _apply(a, b, score_winner=0.5)


def _apply(p1: User, p2: User, score_winner: float) -> tuple[float, float]:
    e1 = _expected(p1.rating, p2.rating)
    e2 = _expected(p2.rating, p1.rating)

    new_p1 = p1.rating + _k_factor(p1) * (score_winner - e1)
    new_p2 = p2.rating + _k_factor(p2) * ((1 - score_winner) - e2)

    p1.rating = round(new_p1, 2)
    p2.rating = round(new_p2, 2)

    p1.rating_deviation = max(30.0, p1.rating_deviation - 5)
    p2.rating_deviation = max(30.0, p2.rating_deviation - 5)

    for u, was in ((p1, True), (p2, False)):
        if u.rating > u.rating_peak:
            u.rating_peak = u.rating
        db.session.add(RatingHistory(user_id=u.id, rating=u.rating))

    return p1.rating, p2.rating
