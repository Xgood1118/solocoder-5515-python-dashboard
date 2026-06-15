import requests
import time
import json

print('=== Alert Simulation Test ===')
print('Simulating high error rate and high latency for service-order...')
print()

SERVICE = 'service-order'
TOKEN = 'token-order-12345'

start_time = time.time()
duration = 45  # 45 seconds to trigger the 30-second duration threshold

print(f'Pushing abnormal metrics for {duration} seconds...')
print('Thresholds:')
print('  error_rate > 1% for 30s -> WARN')
print('  error_rate > 5% for 30s -> CRITICAL')
print('  p99_latency > 500ms for 30s -> WARN')
print('  p99_latency > 1000ms for 30s -> CRITICAL')
print()

count = 0
while time.time() - start_time < duration:
    payloads = []
    
    # High error rate (8% - should trigger critical)
    payloads.append({
        'service': SERVICE,
        'metric': 'error_rate',
        'value': 8.5,
        'timestamp': int(time.time())
    })
    
    # High latency (1200ms - should trigger critical)
    payloads.append({
        'service': SERVICE,
        'metric': 'p99_latency',
        'value': 1200,
        'timestamp': int(time.time())
    })
    
    # Normal QPS
    payloads.append({
        'service': SERVICE,
        'metric': 'qps',
        'value': 150,
        'timestamp': int(time.time())
    })
    
    # CPU and memory normal
    payloads.append({
        'service': SERVICE,
        'metric': 'cpu_usage',
        'value': 45,
        'timestamp': int(time.time())
    })
    
    payloads.append({
        'service': SERVICE,
        'metric': 'memory_usage',
        'value': 55,
        'timestamp': int(time.time())
    })
    
    payloads.append({
        'service': SERVICE,
        'metric': 'disk_usage',
        'value': 60,
        'timestamp': int(time.time())
    })
    
    headers = {'X-Service-Token': TOKEN}
    resp = requests.post('http://127.0.0.1:5000/api/metrics/batch', json={
        'service': SERVICE,
        'metrics': payloads
    }, headers=headers)
    
    count += 1
    if count % 5 == 0:
        print(f'  Batch {count}: status {resp.status_code}')
    
    time.sleep(1)

print()
print(f'Pushed {count} batches of abnormal metrics')
print()

print('=== Checking Current Firing Alerts ===')
resp = requests.get('http://127.0.0.1:5000/api/alerts/firing')
print(f'Status: {resp.status_code}')
alerts = resp.json()
print(json.dumps(alerts, indent=2, ensure_ascii=False))
print()

print('=== Checking All Recent Alerts ===')
resp = requests.get('http://127.0.0.1:5000/api/alerts?limit=10')
print(f'Status: {resp.status_code}')
alerts = resp.json()
for alert in alerts:
    print(f'  [{alert["level"]} {alert["state"]}: {alert["metric_name"]} = {alert["current_value"]} (threshold {alert["direction"]} {alert["threshold_value"]})')
print()

print('=== Checking Service Health Status ===')
resp = requests.get('http://127.0.0.1:5000/api/services')
services = resp.json()
for s in services:
    print(f'  {s["name"]}: {s["health_status"]}')
print()

print('=== Alert simulation completed! ===')
print('Now check the dashboard for alert notifications!')
