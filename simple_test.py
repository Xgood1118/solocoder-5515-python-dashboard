import requests
import time

print('Testing batch API...')

payload = {
    'service': 'service-order',
    'metrics': [
        {
            'metric': 'error_rate',
            'value': 8.5,
            'timestamp': int(time.time())
        },
        {
            'metric': 'p99_latency',
            'value': 1200,
            'timestamp': int(time.time())
        }
    ]
}

headers = {'X-Service-Token': 'token-order-12345'}
resp = requests.post('http://127.0.0.1:5000/api/metrics/batch', json=payload, headers=headers)

print(f'Status: {resp.status_code}')
print(f'Response: {resp.text}')
print()

print('Testing single metric API with header token...')
payload2 = {
    'service': 'service-order',
    'metric': 'qps',
    'value': 150,
    'timestamp': int(time.time())
}
resp2 = requests.post('http://127.0.0.1:5000/api/metrics', json=payload2, headers=headers)
print(f'Status: {resp2.status_code}')
print(f'Response: {resp2.text}')
