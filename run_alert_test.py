import requests
import time
import json

print('=' * 60)
print('SRE 监控仪表板 - 告警模拟测试')
print('=' * 60)
print()

SERVICE = 'service-order'
TOKEN = 'token-order-12345'

print('当前告警状态:')
resp = requests.get('http://127.0.0.1:5000/api/alerts/firing')
alerts = resp.json()
print(f'  当前触发告警: {len(alerts)} 条')
for a in alerts:
    print(f'    - [{a["level"]}] {a["metric_name"]}: {a["current_value"]} (阈值 {a["direction"]} {a["threshold_value"]})')
print()

print('服务健康状态:')
resp = requests.get('http://127.0.0.1:5000/api/services')
services = resp.json()
for s in services:
    status_icon = '✅' if s['health_status'] == 'healthy' else '⚠️' if s['health_status'] == 'warning' else '❌'
    print(f'  {status_icon} {s["name"]}: {s["health_status"]}')
print()

duration = 45
print(f'开始推送异常指标 (持续 {duration} 秒)...')
print('  - error_rate = 8.5% (阈值 > 5% 触发 CRITICAL)')
print('  - p99_latency = 1200ms (阈值 > 1000ms 触发 CRITICAL)')
print()

start_time = time.time()
count = 0

while time.time() - start_time < duration:
    payloads = []
    
    payloads.append({'metric': 'error_rate', 'value': 8.5, 'timestamp': int(time.time())})
    payloads.append({'metric': 'p99_latency', 'value': 1200, 'timestamp': int(time.time())})
    payloads.append({'metric': 'qps', 'value': 150, 'timestamp': int(time.time())})
    payloads.append({'metric': 'cpu_usage', 'value': 45, 'timestamp': int(time.time())})
    payloads.append({'metric': 'memory_usage', 'value': 55, 'timestamp': int(time.time())})
    payloads.append({'metric': 'disk_usage', 'value': 60, 'timestamp': int(time.time())})
    
    headers = {'X-Service-Token': TOKEN}
    resp = requests.post('http://127.0.0.1:5000/api/metrics/batch', json={
        'service': SERVICE,
        'metrics': payloads
    }, headers=headers)
    
    count += 1
    elapsed = int(time.time() - start_time)
    
    if count % 5 == 0:
        print(f'  已推送 {count} 批 (已过 {elapsed}s)...')
    
    time.sleep(1)

print()
print(f'推送完成! 共推送 {count} 批数据')
print()
print('等待 5 秒让告警引擎检测...')
time.sleep(5)
print()

print('=' * 60)
print('测试结果')
print('=' * 60)
print()

print('当前告警状态:')
resp = requests.get('http://127.0.0.1:5000/api/alerts/firing')
alerts = resp.json()
print(f'  当前触发告警: {len(alerts)} 条')
for a in alerts:
    print(f'    - [{a["level"].upper()}] {a["metric_name"]}: {a["current_value"]} (阈值 {a["direction"]} {a["threshold_value"]})')
    print(f'      状态: {a["state"]}, 持续: {a["duration_seconds"]}s')
print()

print('服务健康状态:')
resp = requests.get('http://127.0.0.1:5000/api/services')
services = resp.json()
for s in services:
    status_icon = '✅' if s['health_status'] == 'healthy' else '⚠️' if s['health_status'] == 'warning' else '❌'
    print(f'  {status_icon} {s["name"]}: {s["health_status"]}')
print()

print('最近 5 条告警记录:')
resp = requests.get('http://127.0.0.1:5000/api/alerts?limit=5')
alerts = resp.json()
for a in alerts:
    print(f'  [{a["level"]} {a["state"]}] {a["service_name"]}.{a["metric_name"]} = {a["current_value"]}')
print()

print('=' * 60)
print('测试完成!')
print('=' * 60)
print()
print('请刷新 Dashboard 页面查看实时告警效果!')
