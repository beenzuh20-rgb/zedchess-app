# ZedChess — Chess Betting Platform

A modern, production-quality Flask + SocketIO chess platform inspired by
Lichess, with integrated skill-based betting, Elo rankings, server-authoritative
chess clocks, real-time multiplayer, and a secure wallet.

> This is a full rewrite of the original static `localStorage` prototype into a
> real client/server architecture. The original `*.html` / `*.js` front-end
> files are now superseded by the `zedchess/` package.

## Features

- **Accounts**: register, login, logout, password-reset flow, profile, avatar
  upload, match history, W/L/D stats, Elo rating, earnings, wallet balance,
  online indicator.
- **Home / Landing**: hero, Play Now, online players, open challenges, recent
  winners, leaderboard, dark/light theme, glassmorphism + animations.
- **Lobby (realtime)**: create/join/cancel challenges, spectate, online users,
  player search, friend requests, lobby chat.
- **Betting**: stake presets K5/K10/K20/K50/K100 + custom. Stakes are locked on
  challenge, pot paid to winner minus a configurable platform commission.
- **Live chess**: animated moves, legal-move dots, last-move + check highlights,
  captured pieces, move list, PGN/FEN, promotion popup, board flip, coordinates,
  game-over banner, draw/repetition/insufficient/50-move detection.
- **Clocks**: Lichess-style time controls (Bullet/Blitz/Rapid/Classical), per-side
  timers, increment on completion, red <20s, flash <10s, auto-timeout,
  server-authoritative, survives refresh.
- **Matchmaking**: random, open, private, by-username, friend, rated/casual.
- **Ranking**: Elo, current/peak rating, rating graph, global/weekly/monthly
  leaderboards.
- **Chat**: lobby, game, private messages, mute/block.
- **Notifications**: challenge received/accepted, friend request, match start,
  victory, defeat, wallet updated (toasts + persisted).
- **Wallet**: deposit, withdraw (admin approval), history, pending, available +
  locked balances.
- **Admin**: users (suspend/ban/adjust), withdrawals, active/completed games,
  commission + timer config, stats, announcements.
- **Anti-cheat**: move validation via python-chess, single-session enforcement,
  move-order checks, disconnect forfeit, server-side clocks.
- **Security**: CSRF (Flask-WTF), parameterized queries (SQLAlchemy), auto HTML
  escaping (Jinja2), login rate limiting, password hashing (Werkzeug pbkdf2).

## Architecture

```
zedchess/
  __init__.py        app factory + blueprint/socket registration
  config.py          dev/prod configs (SQLite -> PostgreSQL via DATABASE_URL)
  extensions.py      db, socketio, login, migrate, csrf, mail
  models.py          ORM models (User, Wallet, Game, Challenge, ...)
  services/          business logic (elo, wallet, game, ranking, notify)
  blueprints/        routes (auth, wallet, lobby, game, home, admin)
  sockets/           SocketIO handlers (lobby + game + clock ticker)
  utils/             time_controls, anti_cheat, rate_limit, security
  templates/         Jinja2 templates
  static/            css/js/img
migrations/          Flask-Migrate scripts
run.py               entrypoint (flask-socketio + clock ticker)
seed.py              dev data seed
```

## Quick start (development)

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1    # Windows PowerShell
pip install -r requirements.txt

# Create tables + admin + settings, then seed demo data
python -c "from zedchess import create_app; from zedchess.extensions import db; app=create_app(); \
  app.app_context().push(); db.create_all()"
python seed.py

python run.py                  # use the VENV python, NOT `py run.py`
# open http://localhost:5000
```

> **Note:** the Windows `py` launcher points at the global Python install,
> which does **not** have these packages. Always run `python run.py` from
> inside the activated `.venv` (or `.venv\Scripts\python.exe run.py`). If you
> see `ModuleNotFoundError: No module named 'flask_sqlalchemy'`, you used the
> wrong interpreter.

The app auto-creates an **admin** account:
`admin` / `admin123` (override via `ADMIN_USERNAME` / `ADMIN_PASSWORD` /
`ADMIN_EMAIL` env vars or `.env`).

## Production / PostgreSQL

Set environment variables and switch the database:

```bash
export DATABASE_URL="postgresql+psycopg2://user:pass@host/zedchess"
export SECRET_KEY="a-long-random-string"
export FLASK_ENV=production
flask db upgrade        # apply migrations
python run.py
```

Migrations are managed with Flask-Migrate:

```bash
flask db init           # first time only
flask db migrate -m "msg"
flask db upgrade
```

## Notes / limitations

- The clock ticker runs in a single background thread (fine for one process).
  For multi-worker deployments, move clock state into Redis and run the ticker
  as a worker, or use a task queue.
- Rate limiting and realtime presence are in-memory; replace with Redis in a
  horizontally-scaled deployment (call sites already isolate the limiter/state).
- Password reset emails require a configured SMTP server (`MAIL_*` settings);
  the request endpoint is wired but the send step is intentionally stubbed for
  local dev.
