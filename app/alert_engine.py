import threading
import logging
from datetime import datetime, timedelta
from config import Config
from app.models import db, Metric, Threshold, Alert, Service
from app.ringbuffer import buffer_manager
from app.notifier import notification_manager

logger = logging.getLogger(__name__)

DIRECTION_CN = {
    'gt': '大于',
    'lt': '小于',
    'eq': '等于',
}


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

    def _build_alert_message(self, metric_obj, threshold, current_value, duration_seconds):
        direction_cn = DIRECTION_CN.get(threshold.direction, threshold.direction)
        metric_name = getattr(metric_obj, 'name', 'Unknown') if metric_obj else 'Unknown'
        unit = getattr(metric_obj, 'unit', '') if metric_obj else ''
        unit_str = f' {unit}' if unit else ''
        try:
            threshold_display = f'{float(threshold.threshold_value):.2f}{unit_str}'
        except (TypeError, ValueError):
            threshold_display = f'{threshold.threshold_value}{unit_str}'
        try:
            current_display = f'{float(current_value):.2f}{unit_str}'
        except (TypeError, ValueError):
            current_display = f'{current_value}{unit_str}'
        return f"指标 {metric_name} 当前值 {current_display} {direction_cn} 阈值 {threshold_display}，已持续 {duration_seconds} 秒"

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
                    logger.info(f"Service {service.name} health status -> {new_status}")
            else:
                firing_alerts = Alert.query.filter(
                    Alert.service_id == service_id,
                    Alert.state == 'FIRING'
                ).count()
                if firing_alerts == 0:
                    old_status = service.health_status
                    service.health_status = 'healthy'
                    db.session.commit()
                    if old_status != 'healthy':
                        logger.info(f"Service {service.name} health status -> healthy (was {old_status})")
        except Exception as e:
            logger.error(f"Error updating service health: {e}")
            db.session.rollback()

    def _safe_alert_display(self, alert, metric=None):
        metric_name = ''
        if metric:
            metric_name = getattr(metric, 'name', '')
        if not metric_name:
            m_obj = getattr(alert, 'metric', None)
            if m_obj is not None:
                metric_name = getattr(m_obj, 'name', '')
        service_name = ''
        s_obj = getattr(alert, 'service', None)
        if s_obj is not None:
            service_name = getattr(s_obj, 'name', '')
        if not service_name:
            service_name = f"sid#{alert.service_id}" if alert.service_id else 'unknown_svc'
        metric_name = metric_name or f"mid#{alert.metric_id}" if alert.metric_id else 'unknown_metric'
        return f"{service_name}.{metric_name}"

    def _dispatch_notification(self, alert, threshold, metric_obj, action):
        """Safely dispatch notification, always pass threshold to notifier.
        Also pre-attach fallback attributes for worst-case (detached ORM objects)."""
        try:
            if metric_obj:
                alert._metric_name = metric_obj.name
                alert._metric_unit = metric_obj.unit or ''
            svc_obj = getattr(alert, 'service', None)
            if svc_obj is not None:
                alert._service_name = svc_obj.name

            result = notification_manager.send_alert_with_threshold(alert, threshold, action)
            logger.info(f"Notification dispatched for {action}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to dispatch notification for {action}: {e}", exc_info=True)
            return {}

    def check_metric_thresholds(self, metric):
        results = []
        try:
            current_value = buffer_manager.get_latest_value(metric.id)
            if current_value is None:
                return results

            thresholds = metric.thresholds.filter_by(enabled=True).all()
            if not thresholds:
                return results

            for threshold in thresholds:
                try:
                    values = self._get_metric_values_in_window(metric.id, threshold.duration_seconds)
                    if not values:
                        continue

                    all_breached = all(self._check_threshold(v, threshold) for v in values)
                    duration_so_far = int(len(values) * max(1, (metric.collect_interval or 15)))

                    existing_alert = Alert.query.filter(
                        Alert.metric_id == metric.id,
                        Alert.threshold_id == threshold.id,
                        Alert.state.in_(['OK', 'FIRING'])
                    ).first()

                    if all_breached:
                        if existing_alert and existing_alert.state == 'FIRING':
                            existing_alert.current_value = current_value
                            if existing_alert.started_at:
                                existing_alert.duration_seconds = int(
                                    (datetime.utcnow() - existing_alert.started_at).total_seconds()
                                )
                            else:
                                existing_alert.duration_seconds = duration_so_far
                            existing_alert.message = self._build_alert_message(
                                metric, threshold, current_value, existing_alert.duration_seconds
                            )
                            db.session.commit()
                            results.append(('updated', existing_alert))
                            logger.debug(
                                f"Alert updated: {self._safe_alert_display(existing_alert, metric)} "
                                f"value={current_value} duration={existing_alert.duration_seconds}s"
                            )

                        elif existing_alert and existing_alert.state == 'OK':
                            existing_alert.state = 'FIRING'
                            existing_alert.current_value = current_value
                            existing_alert.started_at = datetime.utcnow()
                            existing_alert.duration_seconds = 0
                            existing_alert.message = self._build_alert_message(
                                metric, threshold, current_value, 0
                            )
                            db.session.commit()

                            logger.info(
                                f"🔔 ALERT FIRING: {self._safe_alert_display(existing_alert, metric)} "
                                f"[{threshold.level}] value={current_value} threshold={threshold.threshold_value}"
                            )

                            if not self._is_suppressed(metric.id, threshold.level):
                                self._dispatch_notification(existing_alert, threshold, metric, 'firing')
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
                                metric, threshold, current_value, 0
                            )
                            db.session.add(new_alert)
                            db.session.commit()

                            logger.info(
                                f"🔔 NEW ALERT FIRING: {self._safe_alert_display(new_alert, metric)} "
                                f"[{threshold.level}] value={current_value} threshold={threshold.threshold_value}"
                            )

                            if not self._is_suppressed(metric.id, threshold.level):
                                self._dispatch_notification(new_alert, threshold, metric, 'firing')
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
                            unit_str = f' {metric.unit}' if getattr(metric, 'unit', '') else ''
                            existing_alert.message = (
                                f"指标 {metric.name} 已恢复正常，当前值 "
                                f"{current_value:.2f}{unit_str}" if isinstance(current_value, float) else
                                f"{current_value}{unit_str}"
                            )
                            db.session.commit()

                            logger.info(
                                f"✅ ALERT RESOLVED: {self._safe_alert_display(existing_alert, metric)} "
                                f"[{threshold.level}] value={current_value}"
                            )

                            self._dispatch_notification(existing_alert, threshold, metric, 'resolved')
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
                    logger.error(
                        f"Error checking threshold {threshold.id} for metric "
                        f"{metric.service_id}.{metric.name}: {e}", exc_info=True
                    )
                    db.session.rollback()

        except Exception as e:
            logger.error(f"Error checking thresholds for metric {metric.id}: {e}", exc_info=True)
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
                firing_count = sum(1 for a, _ in all_results if a == 'firing')
                resolved_count = sum(1 for a, _ in all_results if a == 'resolved')
                updated_count = sum(1 for a, _ in all_results if a == 'updated')
                logger.info(
                    f"Alert cycle completed: {len(all_results)} events "
                    f"(firing={firing_count} resolved={resolved_count} updated={updated_count})"
                )
                for action, alert in all_results:
                    if action in ('firing', 'resolved'):
                        logger.info(
                            f"  {action.upper()}: {self._safe_alert_display(alert)} - {alert.level}"
                        )

            return all_results

        except Exception as e:
            logger.error(f"Error in alert check cycle: {e}", exc_info=True)
            db.session.rollback()
            return []

    def cleanup_suppression_map(self):
        now = datetime.utcnow()
        items = list(self._suppression_map.items())
        expired_keys = [
            key for key, last_time in items
            if (now - last_time).total_seconds() >= Config.ALERT_SUPPRESSION_WINDOW
        ]
        if expired_keys:
            logger.debug(f"Cleaning up {len(expired_keys)} expired suppression entries")
            for key in expired_keys:
                del self._suppression_map[key]


alert_engine = AlertEngine()


def run_alert_engine():
    logger.info("Starting alert engine check cycle")
    try:
        alert_engine.run_check_cycle()
        alert_engine.cleanup_suppression_map()
    except Exception as e:
        logger.error(f"run_alert_engine crashed: {e}", exc_info=True)
