import requests
import time
import json

BASE = 'http://127.0.0.1:5000'
GATEWAY_TOKEN = 'token-gateway-12345'

# 先做一个小预热推送，然后等buffer满
print('=== Pre: push 10 warmup batches of gateway qps=1200, each 3s apart ===')
for i in range(10):
    ts = int(time.time())
    payload = {
        'service': 'service-gateway',
        'metrics': [
            {'metric': 'qps', 'value': 1200, 'timestamp': ts},
            {'metric': 'p99_latency', 'value': 120, 'timestamp': ts},
            {'metric': 'error_rate', 'value': 0.2, 'timestamp': ts},
            {'metric': 'cpu_usage', 'value': 45, 'timestamp': ts},
            {'metric': 'memory_usage', 'value': 55, 'timestamp': ts},
            {'metric': 'disk_usage', 'value': 60, 'timestamp': ts},
        ]
    }
    headers = {'X-Service-Token': GATEWAY_TOKEN}
    r = requests.post(f'{BASE}/api/metrics/batch', json=payload, headers=headers, timeout=5)
    print(f'  batch {i+1}/10: status={r.status_code}, ts={ts}')
    time.sleep(3)

print()
print('Now buffer should have enough samples for duration check. Continuing push for ~65 seconds...')
print()

# 继续推，同时定期检查告警状态
start = time.time()
count = 10
while time.time() - start < 65:
    ts = int(time.time())
    payload = {
        'service': 'service-gateway',
        'metrics': [
            {'metric': 'qps', 'value': 1200, 'timestamp': ts},
            {'metric': 'p99_latency', 'value': 120, 'timestamp': ts},
            {'metric': 'error_rate', 'value': 0.2, 'timestamp': ts},
            {'metric': 'cpu_usage', 'value': 45, 'timestamp': ts},
            {'metric': 'memory_usage', 'value': 55, 'timestamp': ts},
            {'metric': 'disk_usage', 'value': 60, 'timestamp': ts},
        ]
    }
    headers = {'X-Service-Token': GATEWAY_TOKEN}
    try:
        r = requests.post(f'{BASE}/api/metrics/batch', json=payload, headers=headers, timeout=5)
    except Exception as e:
        print(f'  push err: {e}')

    count += 1
    elapsed = int(time.time() - start)

    # 每5批检查一次
    if count % 5 == 0:
        print(f'  ... pushed {count} batches, elapsed={elapsed}s')
        try:
            r = requests.get(f'{BASE}/api/alerts/firing', timeout=5)
            if r.status_code == 200:
                data = r.json()
                alerts = data.get('alerts', [])
                if alerts:
                    print(f'   🔥 FIRING ALERTS: {len(alerts)}')
                    for a in alerts:
                        print(f'      - [{a["level"].upper()}] {a["service_name"]}.{a["metric_name"]} '
                              f'= {a["current_value"]} (threshold {a["direction"]} {a["threshold_value"]}), '
                              f'state={a["state"]} duration={a["duration_seconds"]}s')
                else:
                    print(f'   (no firing alerts yet)')
            else:
                print(f'   ALERTS API ERR: {r.status_code} {r.text[:100]}')

            r2 = requests.get(f'{BASE}/api/services', timeout=5)
            if r2.status_code == 200:
                svc_data = r2.json().get('services', [])
                for s in svc_data:
                    if s['name'] == 'service-gateway':
                        print(f'   gateway health: {s["health_status"]}')
            print()
        except Exception as e:
            print(f'   check err: {e}')

    time.sleep(3)

print()
print('=== Final checks ===')
time.sleep(6)  # 等一个告警引擎周期

print()
print('--- /api/alerts/firing ---')
try:
    r = requests.get(f'{BASE}/api/alerts/firing', timeout=5)
    print(f'Status: {r.status_code}')
    data = r.json()
    print(f'Total firing: {data.get("total", 0)}')
    for a in data.get('alerts', []):
        print(f'  {json.dumps(a, ensure_ascii=False, indent=4)}')
except Exception as e:
    print(f'ERR: {e}')

print()
print('--- /api/alerts?limit=5 ---')
try:
    r = requests.get(f'{BASE}/api/alerts?limit=5', timeout=5)
    print(f'Status: {r.status_code}')
    data = r.json()
    alerts = data.get('alerts', []) if isinstance(data, dict) else data
    print(f'Count: {len(alerts)}')
    for a in alerts:
        keys_ok = 'metric_name' in a and 'service_name' in a
        print(f'  state={a.get("state")} level={a.get("level")} '
              f'{a.get("service_name")}.{a.get("metric_name")} '
              f'keys_ok={keys_ok} msg={str(a.get("message", ""))[:60]}')
except Exception as e:
    print(f'ERR: {e}')

print()
print('--- /api/services ---')
try:
    r = requests.get(f'{BASE}/api/services', timeout=5)
    print(f'Status: {r.status_code}')
    for s in r.json().get('services', []):
        print(f'  {s["name"]}: health={s["health_status"]}')
except Exception as e:
    print(f'ERR: {e}')
