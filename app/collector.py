import threading
import logging
from datetime import datetime, timedelta
from config import Config
from app.models import db, Metric, Service, MetricSample
from app.ringbuffer import buffer_manager

logger = logging.getLogger(__name__)


class MetricCollector:
    def __init__(self):
        self._lock = threading.Lock()

    def validate_token(self, service_name, token):
        expected_token = Config.SERVICE_TOKENS.get(service_name)
        if not expected_token:
            return False
        return token == expected_token

    def get_or_create_service(self, service_name):
        service = Service.query.filter_by(name=service_name).first()
        if not service:
            service = Service(name=service_name, health_status='healthy')
            db.session.add(service)
            db.session.commit()
        return service

    def get_or_create_metric(self, service_id, metric_name, metric_type='gauge', unit='',
                             collect_interval=60, retention_seconds=None, description=''):
        if retention_seconds is None:
            retention_seconds = Config.DEFAULT_SAMPLE_RETENTION

        metric = Metric.query.filter_by(service_id=service_id, name=metric_name).first()
        if not metric:
            metric = Metric(
                service_id=service_id,
                name=metric_name,
                metric_type=metric_type,
                unit=unit,
                collect_interval=collect_interval,
                retention_seconds=retention_seconds,
                description=description
            )
            db.session.add(metric)
            db.session.commit()
        return metric

    def collect(self, service_name, token, metric_name, value, timestamp=None,
                metric_type='gauge', unit='', collect_interval=60,
                retention_seconds=None, description=''):
        if not self.validate_token(service_name, token):
            logger.warning(f"Invalid token for service: {service_name}")
            return False, "Invalid service token"

        if metric_type not in Config.METRIC_TYPES:
            return False, f"Invalid metric type: {metric_type}"

        try:
            value = float(value)
        except (ValueError, TypeError):
            return False, "Invalid metric value"

        if timestamp is None:
            timestamp = datetime.utcnow()
        elif isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp)

        try:
            service = self.get_or_create_service(service_name)
            metric = self.get_or_create_metric(
                service_id=service.id,
                metric_name=metric_name,
                metric_type=metric_type,
                unit=unit,
                collect_interval=collect_interval,
                retention_seconds=retention_seconds,
                description=description
            )

            retention_cutoff = datetime.utcnow() - timedelta(seconds=metric.retention_seconds)
            if timestamp < retention_cutoff:
                return True, "Sample expired, dropped"

            buffer_manager.add_sample(metric.id, value, timestamp)
            logger.debug(f"Collected metric: {service_name}/{metric_name} = {value}")
            return True, "Collected successfully"

        except Exception as e:
            logger.error(f"Error collecting metric: {e}")
            db.session.rollback()
            return False, str(e)

    def collect_batch(self, service_name, token, metrics):
        results = []
        for metric_data in metrics:
            metric_name = metric_data.get('metric') or metric_data.get('name')
            success, message = self.collect(
                service_name=service_name,
                token=token,
                metric_name=metric_name,
                value=metric_data.get('value'),
                timestamp=metric_data.get('timestamp'),
                metric_type=metric_data.get('type', 'gauge'),
                unit=metric_data.get('unit', ''),
                collect_interval=metric_data.get('interval', 60),
                retention_seconds=metric_data.get('retention'),
                description=metric_data.get('description', '')
            )
            results.append({
                'name': metric_name,
                'success': success,
                'message': message
            })
        return results


collector = MetricCollector()


def flush_buffer_to_db():
    try:
        samples = buffer_manager.drain_pending_samples()
        if not samples:
            return

        metric_retention = {}
        valid_samples = []

        for sample in samples:
            metric_id = sample['metric_id']
            if metric_id not in metric_retention:
                metric = Metric.query.get(metric_id)
                if metric:
                    metric_retention[metric_id] = metric.retention_seconds
                else:
                    metric_retention[metric_id] = Config.DEFAULT_SAMPLE_RETENTION

            retention_seconds = metric_retention[metric_id]
            cutoff = datetime.utcnow() - timedelta(seconds=retention_seconds)
            if sample['timestamp'] >= cutoff:
                valid_samples.append(MetricSample(
                    metric_id=sample['metric_id'],
                    value=sample['value'],
                    timestamp=sample['timestamp']
                ))

        if valid_samples:
            db.session.bulk_save_objects(valid_samples)
            db.session.commit()
            logger.info(f"Flushed {len(valid_samples)} samples to database")

    except Exception as e:
        logger.error(f"Error flushing buffer: {e}")
        db.session.rollback()
