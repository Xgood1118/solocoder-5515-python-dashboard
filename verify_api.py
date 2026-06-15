import requests
import time
import json

BASE = 'http://127.0.0.1:5000'

print('=== Test 1: /api/alerts (was returning 500 before fix) ===')
try:
    resp = requests.get(f'{BASE}/api/alerts', timeout=5)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'Type: {type(data)}, len: {len(data) if isinstance(data, list) else "N/A"}')
        if isinstance(data, list):
            for a in data[:3]:
                print(f'  - {a.get("state")} {a.get("level")} {a.get("service_name")}.{a.get("metric_name")} = {a.get("current_value")}')
                print(f'    metric_name present: {"metric_name" in a} -> {a.get("metric_name")!r}')
                print(f'    service_name present: {"service_name" in a} -> {a.get("service_name")!r}')
        else:
            print('Keys:', list(data.keys()))
    else:
        print('ERROR:', resp.text[:500])
except Exception as e:
    print(f'EXCEPTION: {e}')
print()

print('=== Test 2: /api/alerts/firing ===')
try:
    resp = requests.get(f'{BASE}/api/alerts/firing', timeout=5)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict):
            print('Keys:', list(data.keys()))
            for k, v in data.items():
                print(f'  {k}: {v if not isinstance(v, list) else f"list[{len(v)}]"}')
                if isinstance(v, list) and v:
                    for a in v[:2]:
                        print(f'    - {a.get("state")} {a.get("service_name")}.{a.get("metric_name")}')
        else:
            print(f'Type: {type(data)}, len={len(data)}')
    else:
        print('ERROR:', resp.text[:500])
except Exception as e:
    print(f'EXCEPTION: {e}')
print()

print('=== Test 3: /api/services ===')
try:
    resp = requests.get(f'{BASE}/api/services', timeout=5)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        for s in resp.json():
            print(f'  - {s["name"]}: {s["health_status"]}')
except Exception as e:
    print(f'EXCEPTION: {e}')
print()

print('=== Test 4: /api/dashboard/summary ===')
try:
    resp = requests.get(f'{BASE}/api/dashboard/summary', timeout=5)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print('Keys:', list(data.keys()))
        services = data.get('services', [])
        print(f'Services in summary: {len(services)}')
        for s in services[:2]:
            print(f'  - {s.get("name")}: {s.get("health_status")}, metrics={len(s.get("metrics", []))}')
    else:
        print('ERROR:', resp.text[:500])
except Exception as e:
    print(f'EXCEPTION: {e}')
