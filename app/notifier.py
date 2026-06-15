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


class BaseNotifier:
    def send(self, alert, action='firing'):
        raise NotImplementedError

    def _build_message(self, alert, action):
        metric_name = alert.metric.name if alert.metric else 'Unknown Metric'
        service_name = alert.service.name if alert.service else 'Unknown Service'

        if action == 'firing':
            title = f'[ALERT-{alert.level.upper()}] {service_name} - {metric_name}'
        elif action == 'resolved':
            title = f'[RESOLVED] {service_name} - {metric_name}'
        else:
            title = f'[{action.upper()}] {service_name} - {metric_name}'

        direction_text = {
            'gt': '大于',
            'lt': '小于',
            'eq': '等于'
        }.get(alert.direction, alert.direction)

        message = f"""
{title}

服务名称: {service_name}
指标名称: {metric_name}
告警级别: {alert.level}
当前状态: {alert.state}

当前值: {alert.current_value}
阈值: {alert.threshold_value}
条件: 值 {direction_text} 阈值
持续时间: {alert.duration_seconds} 秒

开始时间: {alert.started_at.strftime('%Y-%m-%d %H:%M:%S') if alert.started_at else 'N/A'}
结束时间: {alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else 'N/A'}

告警信息: {alert.message}

-- SRE Monitoring Dashboard
"""
        return title, message.strip()


class EmailNotifier(BaseNotifier):
    def __init__(self):
        self.smtp_host = Config.SMTP_HOST
        self.smtp_port = Config.SMTP_PORT
        self.smtp_user = Config.SMTP_USER
        self.smtp_password = Config.SMTP_PASSWORD
        self.use_tls = Config.SMTP_USE_TLS
        self.recipients = Config.ALERT_RECIPIENTS

    def send(self, alert, action='firing'):
        if not self.smtp_host or not self.recipients:
            logger.warning("Email notifier not configured")
            return False

        try:
            title, message = self._build_message(alert, action)

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

            logger.info(f"Email alert sent: {title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
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

    def send(self, alert, action='firing'):
        if not self.webhook:
            logger.warning("DingTalk notifier not configured")
            return False

        try:
            title, message = self._build_message(alert, action)

            url = self._sign_url() if self.secret else self.webhook

            level_color = {
                'critical': '#FF0000',
                'warn': '#FFA500',
                'info': '#1E90FF'
            }.get(alert.level, '#1E90FF')

            payload = {
                'msgtype': 'markdown',
                'markdown': {
                    'title': title,
                    'text': f'## {title}\n\n{message.replace(chr(10), "  \n")}'
                },
                'at': {
                    'isAtAll': alert.level == 'critical'
                }
            }

            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=10)
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"DingTalk alert sent: {title}")
                return True
            else:
                logger.error(f"DingTalk alert failed: {result}")
                return False
        except Exception as e:
            logger.error(f"Failed to send DingTalk alert: {e}")
            return False


class NotificationManager:
    def __init__(self):
        self._notifiers = {
            'email': EmailNotifier(),
            'dingtalk': DingTalkNotifier(),
        }

    def send_alert(self, alert, action='firing'):
        results = {}
        channel = getattr(alert, 'channel', None)

        if channel and channel in self._notifiers:
            notifier = self._notifiers[channel]
            results[channel] = notifier.send(alert, action)
        else:
            for channel_name, notifier in self._notifiers.items():
                results[channel_name] = notifier.send(alert, action)

        return results

    def send_alert_with_threshold(self, alert, threshold, action='firing'):
        channel = getattr(threshold, 'channel', None)
        if channel and channel in self._notifiers:
            notifier = self._notifiers[channel]
            return {channel: notifier.send(alert, action)}
        return self.send_alert(alert, action)


notification_manager = NotificationManager()
