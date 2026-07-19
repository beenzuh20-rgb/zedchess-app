"""
Real-time notifications service.

Notifies a single user over SocketIO (if connected) *and* persists the event
to the database so it survives reconnects. The client renders a toast and a
badge count from the persisted ``Notification`` rows.
"""

import json

from zedchess.extensions import db, socketio
from zedchess.models import Notification, User


def notify(user_id: int, ntype: str, body: str, data: dict = None) -> None:
    """Persist + push a notification to one user."""
    note = Notification(
        user_id=user_id, type=ntype, body=body,
        data=json.dumps(data or {}),
    )
    db.session.add(note)
    db.session.commit()

    payload = {
        "id": note.id,
        "type": ntype,
        "body": body,
        "data": data or {},
        "created_at": note.created_at.isoformat(),
    }
    socketio.emit("notification", payload, to=f"user_{user_id}")


def notify_many(user_ids: list[int], ntype: str, body: str, data: dict = None):
    for uid in set(user_ids):
        notify(uid, ntype, body, data)


def unread_count(user_id: int) -> int:
    return (
        db.session.query(Notification)
        .filter_by(user_id=user_id, read=False)
        .count()
    )


def mark_read(notification_id: int, user_id: int) -> None:
    note = db.session.get(Notification, notification_id)
    if note and note.user_id == user_id:
        note.read = True
        db.session.commit()


def mark_all_read(user_id: int) -> None:
    (
        db.session.query(Notification)
        .filter_by(user_id=user_id, read=False)
        .update({"read": True})
    )
    db.session.commit()
