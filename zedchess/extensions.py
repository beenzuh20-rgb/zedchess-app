"""Shared Flask extension instances.

Extensions are instantiated here *without* an app object so they can be
imported anywhere (models, blueprints, sockets) and bound later in the
application factory via ``init_app``.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_socketio import SocketIO

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
mail = Mail()
socketio = SocketIO()

# Where Flask-Login redirects unauthenticated users.
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id: str):
    """Flask-Login user loader (defined here to avoid circular imports)."""
    from zedchess.models import User

    return db.session.get(User, int(user_id))
