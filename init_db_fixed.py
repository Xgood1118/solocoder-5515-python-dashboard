import sys
import os
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Service, Metric, Threshold, MetricSample
from config import Config

db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
if os.path.exists(db_path):
    print(f'Removing existing database at {db_path}...')
    os.remove(db_path)

app = create_app()

with app.app_context():
    print('Creating tables...')
    db.create_all()

    SERVICES = [
        {'name': 'service-gateway', 'health_status': 'healthy'},
        {'name': 'service-order', 'health_status': 'healthy'},
        {'name': 'service-user', 'health_status': 'healthy'},
        {'name': 'service-payment', 'health_status': 'healthy'},
    ]

    CORE_METRICS = [
        {'name': 'qps', 'type': 'gauge', 'unit': 'req/s', 'description': '每秒请求数', 'interval': 15},
        {'name': 'p99_latency', 'type': 'gauge', 'unit': 'ms', 'description': 'P99 响应延迟', 'interval': 15},
        {'name': 'error_rate', 'type': 'gauge', 'unit': '%', 'description': '错误率', 'interval': 15},
        {'name': 'cpu_usage', 'type': 'gauge', 'unit': '%', 'description': 'CPU 使用率', 'interval': 15},
        {'name': 'memory_usage', 'type': 'gauge', 'unit': '%', 'description': '内存使用率', 'interval': 15},
        {'name': 'disk_usage', 'type': 'gauge', 'unit': '%', 'description': '磁盘使用率', 'interval': 15},
    ]

    DEFAULT_THRESHOLDS = {
        'qps': [
            {'direction': 'gt', 'threshold_value': 1000, 'duration_seconds': 60, 'level': 'critical', 'channel': 'email'},
            {'direction': 'gt', 'threshold_value': 800, 'duration_seconds': 60, 'level': 'warn', 'channel': 'dingtalk'},
            {'direction': 'lt', 'threshold_value': 10, 'duration_seconds': 120, 'level': 'warn', 'channel': 'dingtalk'},
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

    print('Creating services...')
    for service_data in SERVICES:
        service = Service(**service_data)
        db.session.add(service)
        print(f'  ✅ {service.name}')

    db.session.commit()

    print('Creating metrics and thresholds...')
    total_metrics = 0
    total_thresholds = 0
    services = Service.query.all()
    for service in services:
        for metric_data in CORE_METRICS:
            metric = Metric(
                service_id=service.id,
                name=metric_data['name'],
                metric_type=metric_data['type'],
                unit=metric_data['unit'],
                collect_interval=metric_data.get('interval', 15),
                retention_seconds=Config.DEFAULT_SAMPLE_RETENTION,
                description=metric_data['description']
            )
            db.session.add(metric)
            db.session.flush()
            total_metrics += 1

            if metric_data['name'] in DEFAULT_THRESHOLDS:
                for threshold_data in DEFAULT_THRESHOLDS[metric_data['name']]:
                    threshold = Threshold(
                        metric_id=metric.id,
                        **threshold_data
                    )
                    db.session.add(threshold)
                    total_thresholds += 1

    db.session.commit()
    print(f'  ✅ {total_metrics} metrics, {total_thresholds} thresholds')

    print('Generating 1 hour of historical test data...')
    now = datetime.utcnow()
    start_time = now - timedelta(hours=1)

    samples = []
    current_time = start_time
    base_values = {
        'service-gateway': {'qps': (80, 300), 'p99_latency': (40, 180), 'error_rate': (0, 1.5),
                            'cpu_usage': (30, 65), 'memory_usage': (35, 60), 'disk_usage': (45, 68)},
        'service-order':   {'qps': (50, 180), 'p99_latency': (60, 250), 'error_rate': (0, 2),
                            'cpu_usage': (25, 60), 'memory_usage': (30, 55), 'disk_usage': (40, 65)},
        'service-user':    {'qps': (60, 220), 'p99_latency': (50, 200), 'error_rate': (0, 1),
                            'cpu_usage': (20, 55), 'memory_usage': (25, 50), 'disk_usage': (38, 62)},
        'service-payment': {'qps': (30, 120), 'p99_latency': (80, 320), 'error_rate': (0, 3),
                            'cpu_usage': (22, 58), 'memory_usage': (28, 52), 'disk_usage': (42, 66)},
    }

    while current_time <= now:
        for service in services:
            svc_vals = base_values.get(service.name, {})
            metrics = Metric.query.filter_by(service_id=service.id).all()
            for metric in metrics:
                rng = svc_vals.get(metric.name, (20, 80))
                value = random.uniform(rng[0], rng[1])
                value = max(0, value + random.uniform(-3, 3))
                samples.append(MetricSample(
                    metric_id=metric.id,
                    value=round(value, 4),
                    timestamp=current_time
                ))
        current_time += timedelta(seconds=15)

    db.session.bulk_save_objects(samples)
    db.session.commit()
    print(f'  ✅ {len(samples)} historical samples inserted')

    print()
    print('=' * 60)
    print('Database initialization completed!')
    print('=' * 60)
    print(f'Services: {Service.query.count()}')
    print(f'Metrics:  {Metric.query.count()}')
    print(f'Thresholds: {Threshold.query.count()}')
    print(f'Samples:  {MetricSample.query.count()}')
    print()
    print('Gateway QPS thresholds (for test):')
    gw = Service.query.filter_by(name='service-gateway').first()
    if gw:
        qps_metric = Metric.query.filter_by(service_id=gw.id, name='qps').first()
        if qps_metric:
            for t in qps_metric.thresholds.all():
                symbol = {'>': '>', 'gt': '>', 'lt': '<', 'eq': '='}.get(t.direction, t.direction)
                print(f'  - {t.level.upper()}: qps {symbol} {t.threshold_value} '
                      f'for {t.duration_seconds}s -> {t.channel}')
    print()
    print('Service Tokens:')
    for service_name, token in Config.SERVICE_TOKENS.items():
        print(f'  {service_name}: {token}')
    print()
    print('Database file:', db_path)
