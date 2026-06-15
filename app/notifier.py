import smtplib
import hmac
import base64
import hashlib
import urllib.parse
import time
import logging
import json
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import requests
from config import Config

logger = logging.getLogger(__name__)


DIRECTION_CN = {
    'gt': '大于 (>)',
    'lt': '小于 (<)',
    'eq': '等于 (=)',
}


def _safe_get_service_name(alert):
    obj = getattr(alert, 'service', None)
    if obj is not None:
        name = getattr(obj, 'name', None)
        if name:
            return name
    return ''


def _safe_get_metric_name(alert):
    obj = getattr(alert, 'metric', None)
    if obj is not None:
        name = getattr(obj, 'name', None)
        if name:
            return name
    return ''


def _safe_get_metric_unit(alert):
    obj = getattr(alert, 'metric', None)
    if obj is not None:
        unit = getattr(obj, 'unit', None)
        if unit:
            return unit
    return ''


def _fmt_value(value, unit=''):
    if value is None:
        return 'N/A'
    if isinstance(value, float):
        text = f'{value:.2f}'
    else:
        text = str(value)
    if unit:
        return f'{text} {unit}'
    return text


def _fmt_duration(seconds):
    if not seconds or seconds <= 0:
        return '0 秒'
    s = int(seconds)
    if s < 60:
        return f'{s} 秒'
    m, s = divmod(s, 60)
    if m < 60:
        return f'{m} 分 {s} 秒' if s else f'{m} 分钟'
    h, m = divmod(m, 60)
    return f'{h} 小时 {m} 分'


def _fmt_dt(dt):
    if not dt:
        return 'N/A'
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)


def _build_alert_context(alert, threshold=None, action='firing'):
    service_name = _safe_get_service_name(alert) or getattr(alert, '_service_name', '') or 'Unknown Service'
    metric_name = _safe_get_metric_name(alert) or getattr(alert, '_metric_name', '') or 'Unknown Metric'
    metric_unit = _safe_get_metric_unit(alert) or getattr(alert, '_metric_unit', '') or ''
    direction = alert.direction or (threshold.direction if threshold else '')
    direction_cn = DIRECTION_CN.get(direction, direction or 'N/A')
    duration = _fmt_duration(alert.duration_seconds)
    level = (alert.level or 'info').lower()
    state = alert.state or 'OK'

    current_text = _fmt_value(alert.current_value, metric_unit)
    threshold_text = _fmt_value(alert.threshold_value, metric_unit)

    if action == 'firing':
        status_tag = f'[🚨 {level.upper()} ALERT]'
        headline = f'{service_name} / {metric_name} 触发告警'
    elif action == 'resolved':
        status_tag = f'[✅ RESOLVED]'
        headline = f'{service_name} / {metric_name} 已恢复正常'
    else:
        status_tag = f'[{action.upper()}]'
        headline = f'{service_name} / {metric_name}'

    return {
        'status_tag': status_tag,
        'level': level,
        'action': action,
        'state': state,
        'headline': headline,
        'service_name': service_name,
        'metric_name': metric_name,
        'metric_unit': metric_unit,
        'current_value': alert.current_value,
        'threshold_value': alert.threshold_value,
        'current_text': current_text,
        'threshold_text': threshold_text,
        'direction': direction,
        'direction_cn': direction_cn,
        'duration_seconds': alert.duration_seconds or 0,
        'duration_text': duration,
        'started_at': _fmt_dt(alert.started_at),
        'resolved_at': _fmt_dt(alert.resolved_at),
        'message': alert.message or '',
        'dashboard_url': getattr(Config, 'DASHBOARD_URL', 'http://127.0.0.1:5000/'),
    }


class BaseNotifier:
    def send(self, alert, action='firing', threshold=None):
        raise NotImplementedError

    def build_text_message(self, alert, action, threshold=None):
        ctx = _build_alert_context(alert, threshold, action)
        lines = []
        lines.append(f'{ctx["status_tag"]} {ctx["headline"]}')
        lines.append('')
        lines.append(f'服务名称: {ctx["service_name"]}')
        lines.append(f'指标名称: {ctx["metric_name"]}')
        lines.append(f'告警级别: {ctx["level"].upper()}')
        lines.append(f'当前状态: {ctx["state"]}')
        lines.append('')
        lines.append(f'当前值:   {ctx["current_text"]}')
        lines.append(f'阈 值:   {ctx["threshold_text"]}')
        lines.append(f'条 件:   值 {ctx["direction_cn"]} 阈值')
        lines.append(f'持续时间: {ctx["duration_text"]}')
        lines.append('')
        lines.append(f'开始时间: {ctx["started_at"]}')
        if action == 'resolved':
            lines.append(f'恢复时间: {ctx["resolved_at"]}')
        lines.append('')
        if ctx["message"]:
            lines.append(f'备注信息: {ctx["message"]}')
            lines.append('')
        lines.append(f'Dashboard: {ctx["dashboard_url"]}')
        lines.append('')
        lines.append('-- SRE Monitoring Dashboard --')
        title = f'{ctx["status_tag"]} {ctx["service_name"]}.{ctx["metric_name"]}'
        return title, '\n'.join(lines)

    def build_markdown_message(self, alert, action, threshold=None):
        ctx = _build_alert_context(alert, threshold, action)
        level_emoji = {'critical': '🔴', 'warn': '🟠', 'info': '🔵'}.get(ctx['level'], '⚪')
        lines = []
        lines.append(f'## {level_emoji} {ctx["headline"]}')
        lines.append('')
        lines.append(f'**状态标签**：`{ctx["status_tag"]}`  **告警级别**：`{ctx["level"].upper()}`')
        lines.append('')
        lines.append('### 📊 指标信息')
        lines.append(f'| 项目 | 内容 |')
        lines.append(f'| --- | --- |')
        lines.append(f'| 服务 | `{ctx["service_name"]}` |')
        lines.append(f'| 指标 | `{ctx["metric_name"]}` |')
        lines.append(f'| 当前值 | **{ctx["current_text"]}** |')
        lines.append(f'| 阈值 | {ctx["threshold_text"]} |')
        lines.append(f'| 条件 | 值 {ctx["direction_cn"]} 阈值 |')
        lines.append(f'| 持续时间 | {ctx["duration_text"]} |')
        lines.append('')
        lines.append('### ⏰ 时间线')
        lines.append(f'- 开始时间：{ctx["started_at"]}')
        if action == 'resolved':
            lines.append(f'- 恢复时间：{ctx["resolved_at"]}')
        lines.append('')
        if ctx["message"]:
            lines.append(f'### 📝 备注')
            lines.append(f'> {ctx["message"]}')
            lines.append('')
        lines.append(f'### 🔗 立即排查')
        lines.append(f'[打开 Dashboard →]({ctx["dashboard_url"]})')
        title = f'{level_emoji}{ctx["level"].upper()}: {ctx["service_name"]}.{ctx["metric_name"]}'
        return title, '\n'.join(lines)


class EmailNotifier(BaseNotifier):
    def __init__(self):
        self.smtp_host = Config.SMTP_HOST
        self.smtp_port = Config.SMTP_PORT
        self.smtp_user = Config.SMTP_USER
        self.smtp_password = Config.SMTP_PASSWORD
        self.use_tls = Config.SMTP_USE_TLS
        self.recipients = Config.ALERT_RECIPIENTS

    def send(self, alert, action='firing', threshold=None):
        if not self.smtp_host or not self.recipients:
            logger.warning("Email notifier not configured, skipping")
            return False

        try:
            title, message = self.build_text_message(alert, action, threshold)
            msg = MIMEText(message, 'plain', 'utf-8')
            msg['From'] = Header(f'SRE Monitor <{self.smtp_user}>', 'utf-8')
            msg['To'] = Header(', '.join(self.recipients), 'utf-8')
            msg['Subject'] = Header(title, 'utf-8')

            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            if self.use_tls:
                server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_user, self.recipients, msg.as_string())
            server.quit()

            logger.info(f"Email alert sent successfully: {title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}", exc_info=True)
            return False


class DingTalkNotifier(BaseNotifier):
    def __init__(self):
        self.webhook = Config.DINGTALK_WEBHOOK
        self.secret = Config.DINGTALK_SECRET

    def _sign_url(self):
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return f'{self.webhook}&timestamp={timestamp}&sign={sign}'

    def send(self, alert, action='firing', threshold=None):
        if not self.webhook:
            logger.warning("DingTalk notifier configured (no webhook), skipping")
            return False

        try:
            title, md_text = self.build_markdown_message(alert, action, threshold)
            url = self._sign_url() if self.secret else self.webhook

            is_critical = (alert.level or '').lower() == 'critical'
            payload = {
                'msgtype': 'markdown',
                'markdown': {
                    'title': title,
                    'text': md_text,
                },
                'at': {
                    'isAtAll': is_critical,
                }
            }

            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=10)
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"DingTalk alert sent successfully: {title}")
                return True
            else:
                logger.error(f"DingTalk alert failed: {result}")
                return False
        except Exception as e:
            logger.error(f"Failed to send DingTalk alert: {e}", exc_info=True)
            return False


class NotificationManager:
    def __init__(self):
        self._notifiers = {
            'email': EmailNotifier(),
            'dingtalk': DingTalkNotifier(),
        }

    def send_alert(self, alert, action='firing', threshold=None):
        results = {}
        channel = getattr(alert, 'channel', None)

        if channel and channel in self._notifiers:
            notifier = self._notifiers[channel]
            try:
                results[channel] = notifier.send(alert, action, threshold)
            except Exception as e:
                logger.error(f"Notifier {channel} crashed: {e}", exc_info=True)
                results[channel] = False
        else:
            for channel_name, notifier in self._notifiers.items():
                try:
                    results[channel_name] = notifier.send(alert, action, threshold)
                except Exception as e:
                    logger.error(f"Notifier {channel_name} crashed: {e}", exc_info=True)
                    results[channel_name] = False

        logger.info(f"Notification dispatch ({action}) completed: {results}")
        return results

    def send_alert_with_threshold(self, alert, threshold, action='firing'):
        channel = getattr(threshold, 'channel', None) if threshold else None
        if channel and channel in self._notifiers:
            notifier = self._notifiers[channel]
            try:
                result = notifier.send(alert, action, threshold)
                return {channel: result}
            except Exception as e:
                logger.error(f"Notifier {channel} crashed: {e}", exc_info=True)
                return {channel: False}
        return self.send_alert(alert, action, threshold)


notification_manager = NotificationManager()
