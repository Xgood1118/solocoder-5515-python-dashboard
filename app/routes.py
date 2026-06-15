import json
import time
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, Response, render_template, stream_with_context
from config import Config
from app.models import db, Service, Metric, Threshold, Alert, MetricSample
from app.collector import collector
from app.ringbuffer import buffer_manager
from app.alert_engine import alert_engine

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


def _parse_time_range(time_range):
    if time_range and time_range in Config.TIME_RANGES:
        return Config.TIME_RANGES[time_range]
    try:
        return int(time_range)
    except (ValueError, TypeError):
        return Config.TIME_RANGES['1h']


def _get_metric_by_name_and_service(metric_name, service_name=None):
    query = Metric.query.filter_by(name=metric_name)
    if service_name:
        service = Service.query.filter_by(name=service_name).first()
        if service:
            query = query.filter_by(service_id=service.id)
    return query.first()


@api_bp.route('/metrics', methods=['POST'])
def receive_metric():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'Empty request body'}), 400

        service_name = data.get('service') or data.get('service_name')
        token = request.headers.get('X-Service-Token') or data.get('token')
        metric_name = data.get('metric') or data.get('name')
        value = data.get('value')

        if not all([service_name, token, metric_name, value is not None]):
            return jsonify({'error': 'Missing required fields: service, token (in header X-Service-Token or body), metric, value'}), 400

        success, message = collector.collect(
            service_name=service_name,
            token=token,
            metric_name=metric_name,
            value=value,
            timestamp=data.get('timestamp'),
            metric_type=data.get('type', 'gauge'),
            unit=data.get('unit', ''),
            collect_interval=data.get('interval', 60),
            retention_seconds=data.get('retention'),
            description=data.get('description', '')
        )

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        logger.error(f"Error receiving metric: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/metrics/batch', methods=['POST'])
def receive_metrics_batch():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'Empty request body'}), 400

        service_name = data.get('service') or data.get('service_name')
        token = request.headers.get('X-Service-Token') or data.get('token')
        metrics = data.get('metrics', [])

        if not all([service_name, token]):
            return jsonify({'error': 'Missing required fields: service, token (in header X-Service-Token or body)'}), 400

        if not metrics:
            return jsonify({'error': 'No metrics provided'}), 400

        results = collector.collect_batch(service_name, token, metrics)

        return jsonify({
            'success': True,
            'total': len(metrics),
            'success_count': sum(1 for r in results if r['success']),
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Error receiving metrics batch: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/metrics/query', methods=['GET'])
def query_metrics():
    try:
        metric_name = request.args.get('metric')
        service_name = request.args.get('service')
        time_range = request.args.get('range', '1h')
        seconds = _parse_time_range(time_range)

        if not metric_name:
            return jsonify({'error': 'Missing metric parameter'}), 400

        metric = _get_metric_by_name_and_service(metric_name, service_name)
        if not metric:
            return jsonify({'metric': metric_name, 'data': {'x': [], 'y': []}}), 200

        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        samples = MetricSample.query.filter(
            MetricSample.metric_id == metric.id,
            MetricSample.timestamp >= cutoff
        ).order_by(MetricSample.timestamp).all()

        echarts_data = MetricSample.to_echarts_format(samples)

        return jsonify({
            'metric': metric_name,
            'service': service_name or metric.service.name,
            'metric_id': metric.id,
            'unit': metric.unit,
            'type': metric.metric_type,
            'range_seconds': seconds,
            'data': echarts_data,
            'latest_value': buffer_manager.get_latest_value(metric.id)
        }), 200

    except Exception as e:
        logger.error(f"Error querying metrics: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/metrics/list', methods=['GET'])
def list_metrics():
    try:
        service_name = request.args.get('service')
        query = Metric.query

        if service_name:
            service = Service.query.filter_by(name=service_name).first()
            if service:
                query = query.filter_by(service_id=service.id)

        metrics = query.all()
        return jsonify({
            'metrics': [m.to_dict() for m in metrics],
            'total': len(metrics)
        }), 200

    except Exception as e:
        logger.error(f"Error listing metrics: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/services', methods=['GET'])
def list_services():
    try:
        services = Service.query.all()
        return jsonify({
            'services': [s.to_dict() for s in services],
            'total': len(services)
        }), 200

    except Exception as e:
        logger.error(f"Error listing services: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/services/<service_name>/metrics', methods=['GET'])
def get_service_metrics(service_name):
    try:
        service = Service.query.filter_by(name=service_name).first()
        if not service:
            return jsonify({'error': 'Service not found'}), 404

        metrics = service.metrics.all()
        return jsonify({
            'service': service.to_dict(),
            'metrics': [m.to_dict() for m in metrics],
            'total': len(metrics)
        }), 200

    except Exception as e:
        logger.error(f"Error getting service metrics: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/alerts', methods=['GET'])
def list_alerts():
    try:
        state = request.args.get('state')
        level = request.args.get('level')
        limit = request.args.get('limit', 100, type=int)

        query = Alert.query.order_by(Alert.created_at.desc())

        if state:
            query = query.filter_by(state=state)
        if level:
            query = query.filter_by(level=level)

        alerts = query.limit(limit).all()
        return jsonify({
            'alerts': [a.to_dict() for a in alerts],
            'total': len(alerts)
        }), 200

    except Exception as e:
        logger.error(f"Error listing alerts: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/alerts/firing', methods=['GET'])
def get_firing_alerts():
    try:
        alerts = Alert.query.filter_by(state='FIRING').order_by(Alert.level, Alert.created_at.desc()).all()
        return jsonify({
            'alerts': [a.to_dict() for a in alerts],
            'total': len(alerts)
        }), 200

    except Exception as e:
        logger.error(f"Error getting firing alerts: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/thresholds', methods=['POST'])
def create_threshold():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'Empty request body'}), 400

        metric_id = data.get('metric_id')
        direction = data.get('direction')
        threshold_value = data.get('threshold_value')
        duration_seconds = data.get('duration_seconds', 60)
        level = data.get('level', 'warn')
        channel = data.get('channel', 'email')

        if not all([metric_id, direction, threshold_value is not None]):
            return jsonify({'error': 'Missing required fields: metric_id, direction, threshold_value'}), 400

        if direction not in Config.THRESHOLD_DIRECTIONS:
            return jsonify({'error': f'Invalid direction. Must be one of: {Config.THRESHOLD_DIRECTIONS}'}), 400
        if level not in Config.ALERT_LEVELS:
            return jsonify({'error': f'Invalid level. Must be one of: {Config.ALERT_LEVELS}'}), 400
        if channel not in Config.NOTIFICATION_CHANNELS:
            return jsonify({'error': f'Invalid channel. Must be one of: {Config.NOTIFICATION_CHANNELS}'}), 400

        metric = Metric.query.get(metric_id)
        if not metric:
            return jsonify({'error': 'Metric not found'}), 404

        threshold = Threshold(
            metric_id=metric_id,
            direction=direction,
            threshold_value=float(threshold_value),
            duration_seconds=int(duration_seconds),
            level=level,
            channel=channel,
            enabled=data.get('enabled', True)
        )
        db.session.add(threshold)
        db.session.commit()

        return jsonify({'success': True, 'threshold': threshold.to_dict()}), 201

    except Exception as e:
        logger.error(f"Error creating threshold: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/thresholds/<int:threshold_id>', methods=['DELETE'])
def delete_threshold(threshold_id):
    try:
        threshold = Threshold.query.get(threshold_id)
        if not threshold:
            return jsonify({'error': 'Threshold not found'}), 404

        db.session.delete(threshold)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Threshold deleted'}), 200

    except Exception as e:
        logger.error(f"Error deleting threshold: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dashboard/summary', methods=['GET'])
def get_dashboard_summary():
    try:
        core_metrics = ['qps', 'p99_latency', 'error_rate', 'cpu_usage', 'memory_usage', 'disk_usage']
        services = Service.query.all()

        summary = {
            'services': [],
            'firing_alerts': 0,
            'critical_alerts': 0,
            'warning_alerts': 0
        }

        firing_alerts = Alert.query.filter_by(state='FIRING').all()
        summary['firing_alerts'] = len(firing_alerts)
        summary['critical_alerts'] = sum(1 for a in firing_alerts if a.level == 'critical')
        summary['warning_alerts'] = sum(1 for a in firing_alerts if a.level == 'warn')

        for service in services:
            service_data = {
                'service': service.to_dict(),
                'metrics': {}
            }

            for metric_name in core_metrics:
                metric = Metric.query.filter_by(service_id=service.id, name=metric_name).first()
                if metric:
                    latest_value = buffer_manager.get_latest_value(metric.id)
                    service_data['metrics'][metric_name] = {
                        'metric_id': metric.id,
                        'value': latest_value,
                        'unit': metric.unit,
                        'type': metric.metric_type
                    }
                else:
                    service_data['metrics'][metric_name] = None

            summary['services'].append(service_data)

        return jsonify(summary), 200

    except Exception as e:
        logger.error(f"Error getting dashboard summary: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stream', methods=['GET'])
def stream_metrics():
    def generate():
        last_sent = {}
        while True:
            try:
                data = {}

                metric_ids = buffer_manager.get_all_metric_ids()
                for metric_id in metric_ids:
                    latest = buffer_manager.get_latest_with_time(metric_id)
                    if latest:
                        ts, value = latest
                        ts_str = ts.isoformat()
                        key = str(metric_id)
                        if key not in last_sent or last_sent[key] != ts_str:
                            metric = Metric.query.get(metric_id)
                            if metric:
                                data[key] = {
                                    'metric_id': metric_id,
                                    'metric_name': metric.name,
                                    'service_name': metric.service.name if metric.service else '',
                                    'value': value,
                                    'timestamp': ts_str,
                                    'unit': metric.unit
                                }
                                last_sent[key] = ts_str

                firing_alerts = Alert.query.filter_by(state='FIRING').all()
                if firing_alerts:
                    data['_alerts'] = [a.to_dict() for a in firing_alerts]

                if data:
                    yield f"data: {json.dumps(data)}\n\n"

                time.sleep(2)

            except GeneratorExit:
                break
            except Exception as e:
                logger.error(f"Error in SSE stream: {e}")
                time.sleep(2)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )



