import logging
import signal
import sys
from app import create_app
from app.models import db
from app.scheduler_tasks import init_scheduler, shutdown_scheduler
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_scheduler()
    sys.exit(0)


if __name__ == '__main__':
    app = create_app()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    with app.app_context():
        init_scheduler(app)

    logger.info(f"Starting SRE Monitoring Dashboard on {Config.HOST}:{Config.PORT}")
    logger.info(f"API endpoint: http://{Config.HOST}:{Config.PORT}/api")
    logger.info(f"Dashboard: http://{Config.HOST}:{Config.PORT}/")
    logger.info(f"SSE Stream: http://{Config.HOST}:{Config.PORT}/api/stream")

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=False,
        threaded=True,
        use_reloader=False
    )
