r"""
ZedChess - production-ready Flask chess-betting platform.

Entrypoint. Runs the Flask app behind Flask-SocketIO using the ``threading``
async mode (works out of the box on Windows/dev). For production scale, set
``SOCKETIO_ASYNC_MODE=eventlet`` (already a dependency) and run behind a
worker manager.

IMPORTANT - use the virtualenv's interpreter, NOT the ``py`` launcher, which
resolves to the global Python install (and lacks these packages):

    .venv\Scripts\Activate.ps1
    python run.py

or, without activating:

    .venv\Scripts\python.exe run.py
"""

try:
    from zedchess import create_app
    from zedchess.extensions import socketio
    from zedchess.sockets import start_clock_ticker
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: %s\n"
        "Activate the virtualenv and install requirements first:\n"
        "  .venv\\Scripts\\Activate.ps1\n"
        "  pip install -r requirements.txt\n"
        "Then run with: python run.py  (NOT `py run.py`)" % exc
    )


def main() -> None:
    app = create_app()
    # Start the server-authoritative chess clock ticker.
    start_clock_ticker(socketio)
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
