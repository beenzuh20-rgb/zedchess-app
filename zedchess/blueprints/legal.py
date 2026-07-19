"""
Legal blueprint: static policy pages (Terms of Service, Privacy Policy,
Community Guidelines). Content is rendered from templates; links are surfaced
in the site footer so they are easy to find and link from the signup form.
"""

from flask import Blueprint, render_template

bp = Blueprint("legal", __name__, url_prefix="/legal")


@bp.route("/terms")
def terms():
    return render_template("legal/terms.html")


@bp.route("/privacy")
def privacy():
    return render_template("legal/privacy.html")


@bp.route("/community")
def community():
    return render_template("legal/community.html")
