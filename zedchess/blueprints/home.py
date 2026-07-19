"""
Home / landing blueprint.

Renders the public landing page (hero, leaderboard, recent winners, active
challenge count) and the global leaderboard / ranking pages.
"""

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import current_user

from zedchess.extensions import db
from zedchess.models import User, Game, Settings, Challenge
from zedchess.services.ranking_service import leaderboard, rating_graph

bp = Blueprint("home", __name__)


@bp.route("/")
def index():
    settings = Settings.get(db.session)
    top = leaderboard("global", 10)
    recent_winners = (
        db.session.query(Game)
        .filter(Game.result.in_(["white", "black"]))
        .order_by(Game.id.desc())
        .limit(6)
        .all()
    )
    active_challenges = (
        db.session.query(Challenge)
        .filter_by(status="open")
        .count()
    )
    online_count = (
        db.session.query(User).filter_by(online=True).count()
    )
    return render_template(
        "home/index.html",
        leaderboard=top,
        recent_winners=recent_winners,
        active_challenges=active_challenges,
        online_count=online_count,
        announcement=settings.announcement,
        authenticated=current_user.is_authenticated,
    )


@bp.route("/leaderboard")
def leaderboard_page():
    window = request.args.get("window", "global")
    users = leaderboard(window, 100)
    return render_template(
        "home/leaderboard.html", users=users, window=window,
    )


@bp.route("/rating/<username>")
def rating_graph_page(username):
    user = db.session.query(User).filter_by(username=username).first_or_404()
    points = rating_graph(user.id)
    return render_template(
        "home/rating_graph.html", user=user, points=points,
    )
