import threading
import logging
from datetime import datetime, timedelta
from config import Config
from app.models import db, Metric, Threshold, Alert, Service
from app.ringbuffer import buffer_manager
from app.notifier import notification_manager

logger = logging.getLogger(__name__)


class AlertEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._suppression_map = {}

    def _check_threshold(self, current_value, threshold):
        direction = threshold.direction
        threshold_value = threshold.threshold_value

        if direction == 'gt':
            return current_value > threshold_value
        elif direction == 'lt':
            return current_value < threshold_value
        elif direction == 'eq':
            return abs(current_value - threshold_value) < 0.0001
        return False

    def _get_metric_values_in_window(self, metric_id, duration_seconds):
        data = buffer_manager.get_metric_data(metric_id, duration_seconds)
        if not data:
            return []
        return [v for _, v in data]

    def _is_suppressed(self, metric_id, level):
        key = f"{metric_id}_{level}"
        if key in self._suppression_map:
            last_notified = self._suppression_map[key]
            if (datetime.utcnow() - last_notified).total_seconds() < Config.ALERT_SUPPRESSION_WINDOW:
                return True
        return False

    def _mark_suppressed(self, metric_id, level):
        key = f"{metric_id}_{level}"
        self._suppression_map[key] = datetime.utcnow()

    def _build_alert_message(self, alert, threshold, current_value):
        direction_text = {
            'gt': '大于',
            'lt': '小于',
            'eq': '等于'
        }.get(threshold.direction, threshold.direction)

        return (f"指标 {alert.metric.name} 当前值 {current_value} {direction_text} "
                f"阈值 {threshold.threshold_value}，已持续 {alert.duration_seconds} 秒")

    def _update_service_health(self, service_id, level, is_firing):
        try:
            service = Service.query.get(service_id)
            if not service:
                return

            if is_firing:
                if level == 'critical':
                    new_status = 'critical'
                elif level == 'warn':
                    new_status = 'warning'
                else:
                    new_status = 'degraded'

                if service.health_status in ['healthy', 'degraded'] or \
                   (service.health_status == 'warning' and level == 'critical'):
                    service.health_status = new_status
                    db.session.commit()
            else:
                firing_alerts = Alert.query.filter(
                    Alert.service_id == service_id,
                    Alert.state == 'FIRING'
                ).count()

                if firing_alerts == 0:
                    service.health_status = 'healthy'
                    db.session.commit()

        except Exception as e:
            logger.error(f"Error updating service health: {e}")
            db.session.rollback()

    def check_metric_thresholds(self, metric):
        results = []

        try:
            current_value = buffer_manager.get_latest_value(metric.id)
            if current_value is None:
                return results

            thresholds = metric.thresholds.filter_by(enabled=True).all()

            for threshold in thresholds:
                try:
                    values = self._get_metric_values_in_window(metric.id, threshold.duration_seconds)
                    if not values:
                        continue

                    all_breached = all(self._check_threshold(v, threshold) for v in values)

                    existing_alert = Alert.query.filter(
                        Alert.metric_id == metric.id,
                        Alert.threshold_id == threshold.id,
                        Alert.state.in_(['OK', 'FIRING'])
                    ).first()

                    if all_breached:
                        if existing_alert and existing_alert.state == 'FIRING':
                            existing_alert.current_value = current_value
                            existing_alert.duration_seconds = int(
                                (datetime.utcnow() - existing_alert.started_at).total_seconds()
                            )
                            db.session.commit()
                            results.append(('updated', existing_alert))

                        elif existing_alert and existing_alert.state == 'OK':
                            existing_alert.state = 'FIRING'
                            existing_alert.current_value = current_value
                            existing_alert.started_at = datetime.utcnow()
                            existing_alert.duration_seconds = 0
                            existing_alert.message = self._build_alert_message(
                                existing_alert, threshold, current_value
                            )
                            db.session.commit()

                            if not self._is_suppressed(metric.id, threshold.level):
                                alert_with_channel = existing_alert
                                alert_with_channel.channel = threshold.channel
                                notification_manager.send_alert_with_threshold(
                                    existing_alert, threshold, 'firing'
                                )
                                self._mark_suppressed(metric.id, threshold.level)
                                existing_alert.last_notified_at = datetime.utcnow()
                                db.session.commit()

                            self._update_service_health(metric.service_id, threshold.level, True)
                            results.append(('firing', existing_alert))

                        else:
                            new_alert = Alert(
                                metric_id=metric.id,
                                service_id=metric.service_id,
                                threshold_id=threshold.id,
                                state='FIRING',
                                level=threshold.level,
                                current_value=current_value,
                                threshold_value=threshold.threshold_value,
                                direction=threshold.direction,
                                duration_seconds=0,
                                started_at=datetime.utcnow()
                            )
                            new_alert.message = self._build_alert_message(
                                new_alert, threshold, current_value
                            )
                            db.session.add(new_alert)
                            db.session.commit()

                            if not self._is_suppressed(metric.id, threshold.level):
                                new_alert.channel = threshold.channel
                                notification_manager.send_alert_with_threshold(
                                    new_alert, threshold, 'firing'
                                )
                                self._mark_suppressed(metric.id, threshold.level)
                                new_alert.last_notified_at = datetime.utcnow()
                                db.session.commit()

                            self._update_service_health(metric.service_id, threshold.level, True)
                            results.append(('firing', new_alert))

                    else:
                        if existing_alert and existing_alert.state == 'FIRING':
                            existing_alert.state = 'RESOLVED'
                            existing_alert.resolved_at = datetime.utcnow()
                            existing_alert.current_value = current_value
                            existing_alert.message = f"指标 {metric.name} 已恢复正常，当前值 {current_value}"
                            db.session.commit()

                            existing_alert.channel = threshold.channel
                            notification_manager.send_alert_with_threshold(
                                existing_alert, threshold, 'resolved'
                            )
                            self._update_service_health(metric.service_id, threshold.level, False)
                            results.append(('resolved', existing_alert))

                        elif not existing_alert:
                            new_alert = Alert(
                                metric_id=metric.id,
                                service_id=metric.service_id,
                                threshold_id=threshold.id,
                                state='OK',
                                level=threshold.level,
                                current_value=current_value,
                                threshold_value=threshold.threshold_value,
                                direction=threshold.direction
                            )
                            db.session.add(new_alert)
                            db.session.commit()
                            results.append(('ok', new_alert))

                except Exception as e:
                    logger.error(f"Error checking threshold {threshold.id} for metric {metric.id}: {e}")
                    db.session.rollback()

        except Exception as e:
            logger.error(f"Error checking thresholds for metric {metric.id}: {e}")
            db.session.rollback()

        return results

    def run_check_cycle(self):
        try:
            metrics = Metric.query.all()
            all_results = []
            for metric in metrics:
                results = self.check_metric_thresholds(metric)
                all_results.extend(results)

            if all_results:
                logger.info(f"Alert cycle completed: {len(all_results)} events")
                for action, alert in all_results:
                    if action in ['firing', 'resolved']:
                        logger.info(f"  {action.upper()}: {alert.metric.name if alert.metric else 'unknown'} - {alert.level}")

            return all_results

        except Exception as e:
            logger.error(f"Error in alert check cycle: {e}")
            db.session.rollback()
            return []

    def cleanup_suppression_map(self):
        now = datetime.utcnow()
        expired_keys = [
            key for key, last_time in self._suppression_map.items()
            if (now - last_time).total_seconds() >= Config.ALERT_SUPPRESSION_WINDOW
        ]
        for key in expired_keys:
            del self._suppression_map[key]


alert_engine = AlertEngine()


def run_alert_engine():
    logger.info("Starting alert engine check cycle")
    alert_engine.run_check_cycle()
    alert_engine.cleanup_suppression_map()
