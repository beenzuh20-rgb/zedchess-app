"""
Wallet service.

All balance changes flow through here so the ledger (``Transaction``) stays
consistent and the wallet is always auditable. The wallet keeps two balances:

* ``balance`` — spendable coins,
* ``locked``  — coins currently held in an active betting pot.

A deposit credits ``balance``. A stake *locks* coins (moved balance -> locked).
A payout releases the pot to the winner's ``balance`` and credits
``total_earned``. A refund returns locked coins to ``balance``.
"""

from zedchess.extensions import db
from zedchess.models import Wallet, Transaction, User


def get_or_create_wallet(user_id: int) -> Wallet:
    wallet = db.session.query(Wallet).filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.0, locked=0.0,
                        total_earned=0.0)
        db.session.add(wallet)
        db.session.commit()
    return wallet


def _ledger(wallet: Wallet, amount: float, kind: str, status: str = "completed",
            reference: str = None) -> Transaction:
    tx = Transaction(
        wallet_id=wallet.id, amount=amount, kind=kind,
        status=status, reference=reference,
    )
    db.session.add(tx)
    return tx


def deposit(user_id: int, amount: float, reference: str = None) -> Wallet:
    """Credit spendable balance (admin/faucet deposit)."""
    if amount <= 0:
        raise ValueError("Deposit must be positive")
    wallet = get_or_create_wallet(user_id)
    wallet.balance += amount
    _ledger(wallet, amount, "deposit", reference=reference)
    db.session.commit()
    return wallet


def lock_stake(user_id: int, amount: float, room_id: str) -> None:
    """Move coins from balance into the locked pot for a game.

    Raises ``ValueError`` if the user has insufficient spendable balance so the
    caller can abort the challenge and notify the client.
    """
    if amount <= 0:
        return
    wallet = get_or_create_wallet(user_id)
    if wallet.balance < amount:
        raise ValueError("Insufficient balance to cover stake")
    wallet.balance -= amount
    wallet.locked += amount
    _ledger(wallet, -amount, "stake", reference=room_id)
    db.session.commit()


def unlock_refund(user_id: int, amount: float, room_id: str) -> None:
    """Return locked coins to spendable balance (game aborted / no opponent)."""
    if amount <= 0:
        return
    wallet = get_or_create_wallet(user_id)
    wallet.locked -= amount
    wallet.balance += amount
    _ledger(wallet, amount, "refund", reference=room_id)
    db.session.commit()


def payout_winner(user_id: int, gross: float, room_id: str) -> None:
    """Credit a winner's spendable balance with the net pot."""
    if gross <= 0:
        return
    wallet = get_or_create_wallet(user_id)
    wallet.locked -= min(gross, wallet.locked) if wallet.locked else 0
    wallet.balance += gross
    wallet.total_earned += gross
    # Ledger the net credit; the commission side is recorded as a separate tx
    # against the platform sink (kept out of user wallets).
    _ledger(wallet, gross, "payout", reference=room_id)
    db.session.commit()


def request_withdrawal(user_id: int, amount: float) -> Transaction:
    """Create a pending withdrawal (admin must approve)."""
    if amount <= 0:
        raise ValueError("Withdrawal must be positive")
    wallet = get_or_create_wallet(user_id)
    if wallet.balance < amount:
        raise ValueError("Insufficient balance")
    wallet.balance -= amount
    tx = _ledger(wallet, -amount, "withdraw", status="pending")
    db.session.commit()
    return tx


def approve_withdrawal(tx_id: int) -> None:
    """Mark a pending withdrawal completed (coins already debited on request)."""
    tx = db.session.get(Transaction, tx_id)
    if tx and tx.status == "pending":
        tx.status = "completed"
        db.session.commit()


def reject_withdrawal(tx_id: int, user_id: int, amount: float) -> None:
    """Reject a withdrawal and return the coins to the user's balance."""
    tx = db.session.get(Transaction, tx_id)
    if tx and tx.status == "pending":
        tx.status = "rejected"
        wallet = get_or_create_wallet(user_id)
        wallet.balance += amount
        _ledger(wallet, amount, "refund", reference=f"reject-{tx_id}")
        db.session.commit()


def adjust_balance(user_id: int, delta: float, note: str = None) -> Wallet:
    """Admin manual balance adjustment (can be positive or negative)."""
    wallet = get_or_create_wallet(user_id)
    wallet.balance += delta
    kind = "deposit" if delta >= 0 else "adjust"
    _ledger(wallet, delta, kind, reference=note)
    db.session.commit()
    return wallet


def leaderboard_snapshot(top: int = 50):
    """Top users by rating for the lobby leaderboard."""
    return (
        db.session.query(User)
        .filter(User.is_banned.is_(False))
        .order_by(User.rating.desc())
        .limit(top)
        .all()
    )
