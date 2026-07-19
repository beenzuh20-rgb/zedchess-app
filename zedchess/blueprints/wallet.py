"""
Wallet blueprint: deposit, withdraw (with admin approval), history, balances.
"""

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
)
from flask_login import login_required, current_user

from zedchess.extensions import db
from zedchess.models import Transaction
from zedchess.services.wallet_service import (
    deposit, request_withdrawal, get_or_create_wallet,
)
from zedchess.utils.security import sanitize_text

bp = Blueprint("wallet", __name__, url_prefix="/wallet")


@bp.route("/")
@login_required
def index():
    wallet = get_or_create_wallet(current_user.id)
    txns = wallet.transactions.limit(50).all()
    pending = (
        db.session.query(Transaction)
        .filter_by(wallet_id=wallet.id, status="pending")
        .all()
    )
    return render_template(
        "wallet/index.html",
        wallet=wallet, transactions=txns, pending=pending,
    )


@bp.route("/deposit", methods=["POST"])
@login_required
def do_deposit():
    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        flash("Invalid amount.", "danger")
        return redirect(url_for("wallet.index"))

    if amount <= 0 or amount > 100000:
        flash("Enter an amount between 0 and 100,000.", "danger")
    else:
        # In production this is backed by a payment provider webhook.
        deposit(current_user.id, amount, "manual deposit")
        flash(f"Deposited {amount:.2f}.", "success")
    return redirect(url_for("wallet.index"))


@bp.route("/withdraw", methods=["POST"])
@login_required
def do_withdraw():
    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        flash("Invalid amount.", "danger")
        return redirect(url_for("wallet.index"))

    try:
        request_withdrawal(current_user.id, amount)
        flash("Withdrawal requested. Awaiting admin approval.", "info")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("wallet.index"))
