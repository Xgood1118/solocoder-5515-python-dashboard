import requests
import json
import random
import time

print('=== Testing Dashboard Summary API ===')
resp = requests.get('http://127.0.0.1:5000/api/dashboard/summary')
print(f'Status: {resp.status_code}')
print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
print()

print('=== Testing Services API ===')
resp = requests.get('http://127.0.0.1:5000/api/services')
print(f'Status: {resp.status_code}')
print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
print()

print('=== Testing Metrics List API ===')
resp = requests.get('http://127.0.0.1:5000/api/metrics/list')
print(f'Status: {resp.status_code}')
data = resp.json()
print(f'Got {len(data)} metrics')
for m in data[:5]:
    print(f'  {m["service_name"]}.{m["name"]} ({m["metric_type"]})')
print()

print('=== Testing Metrics Query API (last 1 hour) ===')
resp = requests.get('http://127.0.0.1:5000/api/metrics/query', params={
    'metric_name': 'qps',
    'service_name': 'service-gateway',
    'start_time': int(time.time()) - 3600,
    'end_time': int(time.time())
})
print(f'Status: {resp.status_code}')
data = resp.json()
print(f'Got {len(data.get("data", []))} data points')
print('First few points:')
for point in data.get('data', [])[:3]:
    print(f'  {point}')
print()

print('=== Pushing Real-time Metrics ===')
services = ['service-gateway', 'service-order', 'service-user', 'service-payment']
tokens = {
    'service-gateway': 'token-gateway-12345',
    'service-order': 'token-order-12345',
    'service-user': 'token-user-12345',
    'service-payment': 'token-payment-12345',
}
metrics = ['qps', 'p99_latency', 'error_rate', 'cpu_usage', 'memory_usage', 'disk_usage']

for service in services:
    for metric_name in metrics:
        value = {
            'qps': random.uniform(50, 200),
            'p99_latency': random.uniform(50, 300),
            'error_rate': random.uniform(0, 2),
            'cpu_usage': random.uniform(20, 70),
            'memory_usage': random.uniform(30, 65),
            'disk_usage': random.uniform(40, 70),
        }[metric_name]
        
        payload = {
            'service': service,
            'metric': metric_name,
            'value': round(value, 2),
            'timestamp': int(time.time())
        }
        
        headers = {'X-Service-Token': tokens[service]}
        resp = requests.post('http://127.0.0.1:5000/api/metrics', json=payload, headers=headers)
        print(f'  Pushed {service}.{metric_name} = {round(value,2)}: {resp.status_code}')

print()
print('=== Testing Invalid Token (should fail) ===')
payload = {
    'service': 'service-gateway',
    'metric': 'qps',
    'value': 100,
    'timestamp': int(time.time())
}
headers = {'X-Service-Token': 'invalid-token'}
resp = requests.post('http://127.0.0.1:5000/api/metrics', json=payload, headers=headers)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.json()}')
print()

print('=== Testing Firing Alerts API ===')
resp = requests.get('http://127.0.0.1:5000/api/alerts/firing')
print(f'Status: {resp.status_code}')
print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
print()

print('=== All tests completed! ===')
