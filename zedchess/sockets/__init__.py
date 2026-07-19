"""
Socket package entrypoint.

Exposes ``register_socket_handlers`` (called by the app factory) and a helper
to start the authoritative clock ticker when the server boots.
"""

from zedchess.sockets.handlers import (
    register_socket_handlers as _register,
    start_clock_ticker,
)


def register_socket_handlers(socketio) -> None:
    """Register all SocketIO event handlers."""
    _register(socketio)


__all__ = ["register_socket_handlers", "start_clock_ticker"]
