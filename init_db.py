import sys
import json
import logging
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '.')
from app import create_app
from app.models import db, Service, Metric, Threshold, MetricSample
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICES = [
    {'name': 'service-gateway', 'health_status': 'healthy'},
    {'name': 'service-order', 'health_status': 'healthy'},
    {'name': 'service-user', 'health_status': 'healthy'},
    {'name': 'service-payment', 'health_status': 'healthy'},
]

CORE_METRICS = [
    {'name': 'qps', 'type': 'gauge', 'unit': 'req/s', 'description': '每秒请求数'},
    {'name': 'p99_latency', 'type': 'gauge', 'unit': 'ms', 'description': 'P99 响应延迟'},
    {'name': 'error_rate', 'type': 'gauge', 'unit': '%', 'description': '错误率'},
    {'name': 'cpu_usage', 'type': 'gauge', 'unit': '%', 'description': 'CPU 使用率'},
    {'name': 'memory_usage', 'type': 'gauge', 'unit': '%', 'description': '内存使用率'},
    {'name': 'disk_usage', 'type': 'gauge', 'unit': '%', 'description': '磁盘使用率'},
]

DEFAULT_THRESHOLDS = {
    'qps': [
        {'direction': 'lt', 'threshold_value': 10, 'duration_seconds': 60, 'level': 'warn', 'channel': 'dingtalk'},
    ],
    'p99_latency': [
        {'direction': 'gt', 'threshold_value': 500, 'duration_seconds': 30, 'level': 'warn', 'channel': 'dingtalk'},
        {'direction': 'gt', 'threshold_value': 1000, 'duration_seconds': 30, 'level': 'critical', 'channel': 'email'},
    ],
    'error_rate': [
        {'direction': 'gt', 'threshold_value': 1, 'duration_seconds': 30, 'level': 'warn', 'channel': 'dingtalk'},
        {'direction': 'gt', 'threshold_value': 5, 'duration_seconds': 30, 'level': 'critical', 'channel': 'email'},
    ],
    'cpu_usage': [
        {'direction': 'gt', 'threshold_value': 70, 'duration_seconds': 60, 'level': 'warn', 'channel': 'dingtalk'},
        {'direction': 'gt', 'threshold_value': 90, 'duration_seconds': 60, 'level': 'critical', 'channel': 'email'},
    ],
    'memory_usage': [
        {'direction': 'gt', 'threshold_value': 75, 'duration_seconds': 60, 'level': 'warn', 'channel': 'dingtalk'},
        {'direction': 'gt', 'threshold_value': 90, 'duration_seconds': 60, 'level': 'critical', 'channel': 'email'},
    ],
    'disk_usage': [
        {'direction': 'gt', 'threshold_value': 80, 'duration_seconds': 3600, 'level': 'warn', 'channel': 'dingtalk'},
        {'direction': 'gt', 'threshold_value': 95, 'duration_seconds': 3600, 'level': 'critical', 'channel': 'email'},
    ],
}


def init_database():
    app = create_app()

    with app.app_context():
        logger.info("Dropping all existing tables...")
        db.drop_all()

        logger.info("Creating all tables...")
        db.create_all()

        logger.info("Creating services...")
        for service_data in SERVICES:
            service = Service(**service_data)
            db.session.add(service)
            logger.info(f"  Created service: {service.name}")

        db.session.commit()

        logger.info("Creating metrics and thresholds...")
        services = Service.query.all()
        for service in services:
            for metric_data in CORE_METRICS:
                metric = Metric(
                    service_id=service.id,
                    name=metric_data['name'],
                    metric_type=metric_data['type'],
                    unit=metric_data['unit'],
                    collect_interval=15,
                    retention_seconds=Config.DEFAULT_SAMPLE_RETENTION,
                    description=metric_data['description']
                )
                db.session.add(metric)
                db.session.flush()

                if metric_data['name'] in DEFAULT_THRESHOLDS:
                    for threshold_data in DEFAULT_THRESHOLDS[metric_data['name']]:
                        threshold = Threshold(
                            metric_id=metric.id,
                            **threshold_data
                        )
                        db.session.add(threshold)

                logger.info(f"  Created metric: {service.name}/{metric.name} with {len(DEFAULT_THRESHOLDS.get(metric_data['name'], []))} thresholds")

        db.session.commit()

        logger.info("\nGenerating historical test data (last 1 hour)...")
        generate_historical_data()

        logger.info("\nDatabase initialization completed!")
        print_service_tokens()


def generate_historical_data():
    import random

    services = Service.query.all()
    now = datetime.utcnow()
    start_time = now - timedelta(hours=1)

    samples = []
    current_time = start_time

    while current_time <= now:
        for service in services:
            metrics = Metric.query.filter_by(service_id=service.id).all()
            for metric in metrics:
                base_value = {
                    'qps': random.uniform(50, 200),
                    'p99_latency': random.uniform(50, 300),
                    'error_rate': random.uniform(0, 2),
                    'cpu_usage': random.uniform(20, 70),
                    'memory_usage': random.uniform(30, 65),
                    'disk_usage': random.uniform(40, 70),
                }.get(metric.name, 50)

                noise = random.uniform(-5, 5)
                value = max(0, base_value + noise)

                samples.append(MetricSample(
                    metric_id=metric.id,
                    value=value,
                    timestamp=current_time
                ))

        current_time += timedelta(seconds=15)

    db.session.bulk_save_objects(samples)
    db.session.commit()
    logger.info(f"Generated {len(samples)} historical samples")


def print_service_tokens():
    logger.info("\n" + "=" * 60)
    logger.info("Service Tokens (for metric push authentication):")
    logger.info("=" * 60)
    for service_name, token in Config.SERVICE_TOKENS.items():
        logger.info(f"  {service_name}: {token}")
    logger.info("=" * 60)


def show_help():
    print("""
SRE Monitoring Dashboard - Database Initialization Script

Usage:
    python init_db.py          Initialize database with default data
    python init_db.py --help   Show this help message

Description:
    This script will:
    1. Drop all existing tables (WARNING: All data will be lost!)
    2. Create fresh tables
    3. Create default services (4 services)
    4. Create core metrics (6 metrics per service)
    5. Configure default thresholds for each metric
    6. Generate 1 hour of historical test data
    7. Display service tokens for API authentication
    """)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        show_help()
        sys.exit(0)

    print("\n" + "=" * 60)
    print("WARNING: This will DELETE all existing data in the database!")
    print("=" * 60)

    response = input("\nAre you sure you want to continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Operation cancelled.")
        sys.exit(0)

    init_database()
