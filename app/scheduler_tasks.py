import logging
from datetime import datetime, timedelta
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config import Config
from app.models import db, MetricSample
from app.collector import flush_buffer_to_db
from app.alert_engine import run_alert_engine

logger = logging.getLogger(__name__)

scheduler = None
_app = None


def with_app_context(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if _app is None:
            logger.error("App context not available for scheduled task")
            return
        with _app.app_context():
            return f(*args, **kwargs)
    return wrapper


@with_app_context
def cleanup_old_data():
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=Config.RETENTION_DAYS)
        deleted = MetricSample.query.filter(MetricSample.timestamp < cutoff_date).delete()
        db.session.commit()
        logger.info(f"Cleanup task: deleted {deleted} old metric samples")
    except Exception as e:
        logger.error(f"Error in cleanup task: {e}")
        db.session.rollback()


@with_app_context
def flush_buffer_to_db_scheduled():
    flush_buffer_to_db()


@with_app_context
def run_alert_engine_scheduled():
    run_alert_engine()


def init_scheduler(app):
    global scheduler, _app
    _app = app

    scheduler = BackgroundScheduler(timezone='UTC')

    scheduler.add_job(
        flush_buffer_to_db_scheduled,
        trigger=IntervalTrigger(seconds=Config.FLUSH_INTERVAL),
        id='flush_buffer',
        name='Flush metric buffer to database',
        replace_existing=True
    )
    logger.info(f"Scheduled flush task every {Config.FLUSH_INTERVAL} seconds")

    scheduler.add_job(
        run_alert_engine_scheduled,
        trigger=IntervalTrigger(seconds=Config.ALERT_CHECK_INTERVAL),
        id='alert_engine',
        name='Run alert engine check cycle',
        replace_existing=True
    )
    logger.info(f"Scheduled alert engine every {Config.ALERT_CHECK_INTERVAL} seconds")

    scheduler.add_job(
        cleanup_old_data,
        trigger=CronTrigger(
            hour=Config.CLEANUP_SCHEDULE_HOUR,
            minute=Config.CLEANUP_SCHEDULE_MINUTE
        ),
        id='cleanup_old_data',
        name='Clean up old metric samples',
        replace_existing=True
    )
    logger.info(f"Scheduled cleanup task at {Config.CLEANUP_SCHEDULE_HOUR:02d}:{Config.CLEANUP_SCHEDULE_MINUTE:02d} UTC daily")

    scheduler.start()
    logger.info("Scheduler started successfully")

    return scheduler


def shutdown_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler shutdown successfully")
