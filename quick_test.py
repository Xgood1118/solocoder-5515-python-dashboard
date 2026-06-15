import requests
import time

print('Pushing abnormal metrics for 35 seconds...')
for i in range(35):
    payload = {
        'service': 'service-order',
        'metrics': [
            {'metric': 'error_rate', 'value': 10.0, 'timestamp': int(time.time())},
            {'metric': 'p99_latency', 'value': 1500, 'timestamp': int(time.time())},
        ]
    }
    headers = {'X-Service-Token': 'token-order-12345'}
    r = requests.post('http://127.0.0.1:5000/api/metrics/batch', json=payload, headers=headers)
    if i % 10 == 0:
        print('  Batch ' + str(i+1) + ': ' + str(r.status_code))
    time.sleep(1)

print('Done pushing, waiting 5s for alert engine...')
time.sleep(5)

print()
r = requests.get('http://127.0.0.1:5000/api/alerts/firing')
data = r.json()
print('Firing API response keys: ' + str(list(data.keys())))
print('Total alerts: ' + str(data.get('total', 0)))
print('Alerts list length: ' + str(len(data.get('alerts', []))))
for a in data.get('alerts', []):
    print('  - ' + str(a))

print()
r = requests.get('http://127.0.0.1:5000/api/alerts?limit=5')
alerts = r.json()
print('Alerts API (limit=5): ' + str(len(alerts)) + ' items')
for a in alerts[:3]:
    print('  ' + str(a))

print()
r = requests.get('http://127.0.0.1:5000/api/services')
print('Service statuses:')
for s in r.json():
    print('  ' + s['name'] + ': ' + s['health_status'])
