import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from app.notifier import BaseNotifier, _build_alert_context
from app.models import Metric, Service, Threshold, Alert

# 模拟几个对象，不需要数据库
class FakeMetric:
    name = 'qps'
    unit = 'req/s'
    metric_type = 'gauge'

class FakeService:
    name = 'service-gateway'

class FakeThreshold:
    direction = 'gt'
    threshold_value = 1000.0
    duration_seconds = 60
    level = 'critical'
    channel = 'email'

class FakeAlert:
    metric = FakeMetric()
    service = FakeService()
    metric_id = 1
    service_id = 1
    threshold_id = 1
    state = 'FIRING'
    level = 'critical'
    current_value = 1200.0
    threshold_value = 1000.0
    direction = 'gt'
    duration_seconds = 67
    started_at = datetime.utcnow() - timedelta(seconds=67)
    resolved_at = None
    message = '指标 qps 当前值 1200.00 req/s 大于 阈值 1000.00 req/s，已持续 67 秒'

print('=' * 70)
print('📧 Email 通知内容 (纯文本)')
print('=' * 70)
bn = BaseNotifier()
title, msg = bn.build_text_message(FakeAlert(), 'firing', FakeThreshold())
print(f'SUBJECT: {title}')
print('-' * 70)
print(msg)
print()

print('=' * 70)
print('🔔 钉钉通知内容 (Markdown)')
print('=' * 70)
title2, md = bn.build_markdown_message(FakeAlert(), 'firing', FakeThreshold())
print(f'TITLE: {title2}')
print('-' * 70)
print(md)
print()

print('=' * 70)
print('✅ RESOLVED 通知内容 (对比用)')
print('=' * 70)
FakeAlert.state = 'RESOLVED'
FakeAlert.resolved_at = datetime.utcnow()
FakeAlert.duration_seconds = 300
title3, msg3 = bn.build_text_message(FakeAlert(), 'resolved', FakeThreshold())
print(f'SUBJECT: {title3}')
print('-' * 70)
print(msg3)
print()

print('=' * 70)
print('🔍 Alert Context 字段完整性检查')
print('=' * 70)
FakeAlert.state = 'FIRING'
ctx = _build_alert_context(FakeAlert(), FakeThreshold(), 'firing')
for k, v in ctx.items():
    print(f'  {k:20s}: {v!r}')
