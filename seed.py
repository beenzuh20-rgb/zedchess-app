"""
Development seeding script.

Creates a handful of demo players with wallets, a few completed games, and
some open challenges so the lobby/leaderboard look alive in development.

Run:
    python seed.py
"""

import os
import random

from zedchess import create_app
from zedchess.extensions import db
from zedchess.models import (
    User, Game, Challenge, RatingHistory, Settings,
)
from zedchess.services.wallet_service import deposit, get_or_create_wallet


def seed() -> None:
    app = create_app()
    with app.app_context():
        Settings.get(db.session)

        names = ["magnus", "hikaru", "ding", "fabiano", "alireza",
                 "levon", "wes", "alex", "sam", "nova"]
        users = []
        for i, name in enumerate(names, start=1):
            if db.session.query(User).filter_by(username=name).first():
                continue
            u = User(
                username=name,
                email=f"{name}@example.com",
                rating=1200 + random.randint(-150, 350),
                rating_peak=1500,
            )
            u.set_password("password123")
            db.session.add(u)
            db.session.flush()
            get_or_create_wallet(u.id)
            deposit(u.id, 1000.0 + i * 50, "seed")
            db.session.add(RatingHistory(user_id=u.id, rating=u.rating))
            users.append(u)
        db.session.commit()

        # A couple of open challenges.
        challenger = db.session.query(User).filter_by(username="magnus").first()
        if challenger and not db.session.query(Challenge).first():
            for tc, stake in [("5+3", 10), ("3+2", 0), ("10+5", 50)]:
                db.session.add(Challenge(
                    challenger_id=challenger.id, time_control=tc,
                    stake=stake, rated=True, status="open",
                ))
        db.session.commit()
        print("Seed complete. Demo users (password: password123):", names)


if __name__ == "__main__":
    seed()
