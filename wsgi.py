"""
WSGI entry point for Render (Gunicorn + eventlet).

Usage on Render:
    gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT wsgi:app

Note: Flask-SocketIO requires eventlet workers and only ONE worker process.
"""

from zedchess import create_app
from zedchess.extensions import socketio
from zedchess.sockets import start_clock_ticker

app = create_app()

# Start the server-authoritative chess clock ticker.
start_clock_ticker(socketio)