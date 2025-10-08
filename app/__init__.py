from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from .config import Config
from flask_cors import CORS


db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    CORS(app)

    from app import models

    # Initialize Firebase Admin SDK
    from app.firebase_config import initialize_firebase
    initialize_firebase()
    
    from app.routes import routes
    app.register_blueprint(routes)

    # Ensure database sessions are properly closed after each request
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    return app
