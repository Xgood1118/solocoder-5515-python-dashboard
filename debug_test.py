import requests
import time

metric_data = {
    'metric': 'error_rate',
    'value': 8.5,
    'timestamp': int(time.time())
}

print(f"metric_data: {metric_data}")
print(f"metric_data.get('metric'): {metric_data.get('metric')}")
print(f"metric_data.get('name'): {metric_data.get('name')}")
print(f"metric_data.get('metric') or metric_data.get('name'): {metric_data.get('metric') or metric_data.get('name')}")
print()

payload = {
    'service': 'service-order',
    'metrics': [metric_data]
}

headers = {'X-Service-Token': 'token-order-12345'}
print(f"Sending payload: {payload}")
resp = requests.post('http://127.0.0.1:5000/api/metrics/batch', json=payload, headers=headers)

print(f'Status: {resp.status_code}')
print(f'Response: {resp.text}')
