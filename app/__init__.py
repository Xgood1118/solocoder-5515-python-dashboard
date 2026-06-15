import logging
import sys
from flask import Flask
from config import Config
from app.models import db
from app.routes import api_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(Config)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        logger.info("Database tables created successfully")

    app.register_blueprint(api_bp, url_prefix='/api')

    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    return app
