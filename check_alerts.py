import requests
import json
import time

print('=== 当前告警状态 ===')
resp = requests.get('http://127.0.0.1:5000/api/alerts/firing')
alerts = resp.json()
print(f'触发中: {len(alerts)}')
for a in alerts:
    print(f'  [{a["level"]}] {a["service_name"]}.{a["metric_name"]} = {a["current_value"]}')

print()
print('=== 服务状态 ===')
resp = requests.get('http://127.0.0.1:5000/api/services')
for s in resp.json():
    print(f'  {s["name"]}: {s["health_status"]}')

print()
print('=== 推送异常数据 (error_rate=10%, p99=1500ms) ===')

for i in range(35):
    payload = {
        'service': 'service-order',
        'metrics': [
            {'metric': 'error_rate', 'value': 10.0, 'timestamp': int(time.time())},
            {'metric': 'p99_latency', 'value': 1500, 'timestamp': int(time.time())},
            {'metric': 'qps', 'value': 120, 'timestamp': int(time.time())},
        ]
    }
    headers = {'X-Service-Token': 'token-order-12345'}
    resp = requests.post('http://127.0.0.1:5000/api/metrics/batch', json=payload, headers=headers)
    if i % 5 == 0:
        print(f'  推送 {i+1}/35, status={resp.status_code}')
    time.sleep(1)

print()
print('等待5秒让告警引擎检测...')
time.sleep(5)

print()
print('=== 检测后告警状态 ===')
resp = requests.get('http://127.0.0.1:5000/api/alerts/firing')
alerts = resp.json()
print(f'触发中: {len(alerts)}')
for a in alerts:
    print(f'  [{a["level"].upper()}] {a["service_name"]}.{a["metric_name"]}')
    print(f'    当前值: {a["current_value"]}, 阈值: {a["direction"]} {a["threshold_value"]}')
    print(f'    状态: {a["state"]}, 持续: {a["duration_seconds"]}s')

print()
print('=== 服务状态 ===')
resp = requests.get('http://127.0.0.1:5000/api/services')
for s in resp.json():
    print(f'  {s["name"]}: {s["health_status"]}')
