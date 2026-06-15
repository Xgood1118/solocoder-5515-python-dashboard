import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'sre-dashboard-secret-key-2024')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "monitor.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'connect_args': {'check_same_thread': False}}

    PORT = int(os.environ.get('PORT', 5000))
    HOST = os.environ.get('HOST', '0.0.0.0')

    SERVICE_TOKENS = {
        'service-order': 'token-order-12345',
        'service-user': 'token-user-12345',
        'service-payment': 'token-payment-12345',
        'service-gateway': 'token-gateway-12345',
    }

    RINGBUFFER_CAPACITY = 3600
    RINGBUFFER_DURATION = 3600
    FLUSH_INTERVAL = 10

    ALERT_CHECK_INTERVAL = 5
    ALERT_SUPPRESSION_WINDOW = 1800
    ALERT_STATES = ['OK', 'FIRING', 'RESOLVED']

    RETENTION_DAYS = 7
    CLEANUP_SCHEDULE_HOUR = 3
    CLEANUP_SCHEDULE_MINUTE = 0

    DEFAULT_SAMPLE_RETENTION = 86400

    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.example.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USER = os.environ.get('SMTP_USER', 'alert@example.com')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', 'password')
    SMTP_USE_TLS = True
    ALERT_RECIPIENTS = ['oncall@example.com']

    DINGTALK_WEBHOOK = os.environ.get('DINGTALK_WEBHOOK', '')
    DINGTALK_SECRET = os.environ.get('DINGTALK_SECRET', '')

    METRIC_TYPES = ['counter', 'histogram', 'gauge']
    ALERT_LEVELS = ['info', 'warn', 'critical']
    THRESHOLD_DIRECTIONS = ['gt', 'lt', 'eq']
    NOTIFICATION_CHANNELS = ['email', 'dingtalk']

    TIME_RANGES = {
        '5m': 300,
        '1h': 3600,
        '6h': 21600,
        '24h': 86400,
    }
