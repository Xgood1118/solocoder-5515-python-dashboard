import sys
import time
import json
import random
import logging
import requests
from datetime import datetime
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_URL = 'http://localhost:5000/api/metrics'

SERVICE_CONFIG = {
    'service-gateway': {
        'token': Config.SERVICE_TOKENS['service-gateway'],
        'metrics': {
            'qps': {'base': 150, 'variance': 50, 'min': 10, 'max': 500},
            'p99_latency': {'base': 100, 'variance': 80, 'min': 20, 'max': 2000},
            'error_rate': {'base': 0.3, 'variance': 0.5, 'min': 0, 'max': 100},
            'cpu_usage': {'base': 45, 'variance': 20, 'min': 10, 'max': 100},
            'memory_usage': {'base': 60, 'variance': 10, 'min': 20, 'max': 100},
            'disk_usage': {'base': 55, 'variance': 5, 'min': 20, 'max': 100},
        }
    },
    'service-order': {
        'token': Config.SERVICE_TOKENS['service-order'],
        'metrics': {
            'qps': {'base': 80, 'variance': 40, 'min': 5, 'max': 300},
            'p99_latency': {'base': 200, 'variance': 150, 'min': 30, 'max': 3000},
            'error_rate': {'base': 0.5, 'variance': 0.8, 'min': 0, 'max': 100},
            'cpu_usage': {'base': 50, 'variance': 25, 'min': 10, 'max': 100},
            'memory_usage': {'base': 55, 'variance': 15, 'min': 20, 'max': 100},
            'disk_usage': {'base': 60, 'variance': 5, 'min': 20, 'max': 100},
        }
    },
    'service-user': {
        'token': Config.SERVICE_TOKENS['service-user'],
        'metrics': {
            'qps': {'base': 120, 'variance': 60, 'min': 10, 'max': 400},
            'p99_latency': {'base': 80, 'variance': 60, 'min': 15, 'max': 1500},
            'error_rate': {'base': 0.2, 'variance': 0.3, 'min': 0, 'max': 100},
            'cpu_usage': {'base': 40, 'variance': 15, 'min': 10, 'max': 100},
            'memory_usage': {'base': 65, 'variance': 10, 'min': 20, 'max': 100},
            'disk_usage': {'base': 50, 'variance': 5, 'min': 20, 'max': 100},
        }
    },
    'service-payment': {
        'token': Config.SERVICE_TOKENS['service-payment'],
        'metrics': {
            'qps': {'base': 40, 'variance': 20, 'min': 5, 'max': 150},
            'p99_latency': {'base': 300, 'variance': 200, 'min': 50, 'max': 5000},
            'error_rate': {'base': 0.1, 'variance': 0.2, 'min': 0, 'max': 100},
            'cpu_usage': {'base': 35, 'variance': 15, 'min': 10, 'max': 100},
            'memory_usage': {'base': 70, 'variance': 10, 'min': 20, 'max': 100},
            'disk_usage': {'base': 45, 'variance': 5, 'min': 20, 'max': 100},
        }
    }
}


def generate_metric_value(config):
    value = config['base'] + random.uniform(-config['variance'], config['variance'])
    return max(config['min'], min(config['max'], value))


def push_metric(service_name, token, metric_name, value, metric_type='gauge', unit=''):
    try:
        payload = {
            'service': service_name,
            'token': token,
            'metric': metric_name,
            'value': value,
            'type': metric_type,
            'unit': unit,
            'timestamp': datetime.utcnow().timestamp()
        }

        response = requests.post(API_URL, json=payload, timeout=5)
        result = response.json()

        if result.get('success'):
            logger.info(f"✓ {service_name}/{metric_name} = {value:.2f}")
            return True
        else:
            logger.error(f"✗ {service_name}/{metric_name} failed: {result.get('error')}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Connection error for {service_name}/{metric_name}: {e}")
        return False


def push_batch_metrics(service_name, token, metrics_data):
    try:
        payload = {
            'service': service_name,
            'token': token,
            'metrics': metrics_data
        }

        response = requests.post(API_URL + '/batch', json=payload, timeout=5)
        result = response.json()

        if result.get('success'):
            success_count = result.get('success_count', 0)
            total = result.get('total', 0)
            logger.info(f"✓ {service_name}: {success_count}/{total} metrics pushed")
            return True
        else:
            logger.error(f"✗ {service_name} batch failed: {result.get('error')}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Connection error for {service_name} batch: {e}")
        return False


def run_single_push(use_batch=True):
    logger.info("=" * 60)
    logger.info(f"Pushing metrics ({'batch' if use_batch else 'individual'} mode)...")
    logger.info("=" * 60)

    for service_name, service_config in SERVICE_CONFIG.items():
        if use_batch:
            metrics_data = []
            for metric_name, metric_config in service_config['metrics'].items():
                value = generate_metric_value(metric_config)
                metrics_data.append({
                    'name': metric_name,
                    'value': value,
                    'type': 'gauge',
                    'unit': metric_config.get('unit', '')
                })
            push_batch_metrics(service_name, service_config['token'], metrics_data)
        else:
            for metric_name, metric_config in service_config['metrics'].items():
                value = generate_metric_value(metric_config)
                push_metric(
                    service_name,
                    service_config['token'],
                    metric_name,
                    value,
                    unit=metric_config.get('unit', '')
                )

    logger.info("")


def run_continuous_push(interval=5, use_batch=True, duration=None):
    logger.info("Starting continuous metric push...")
    logger.info(f"Push interval: {interval}s, Mode: {'batch' if use_batch else 'individual'}")
    if duration:
        logger.info(f"Duration: {duration}s")

    start_time = time.time()
    push_count = 0

    try:
        while True:
            run_single_push(use_batch)
            push_count += 1

            if duration and (time.time() - start_time) >= duration:
                logger.info(f"\nDuration reached. Total pushes: {push_count}")
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info(f"\nInterrupted by user. Total pushes: {push_count}")


def simulate_alert_scenario():
    logger.info("\n" + "=" * 60)
    logger.info("SIMULATING ALERT SCENARIO - High Error Rate")
    logger.info("=" * 60)

    service_name = 'service-order'
    service_config = SERVICE_CONFIG[service_name]

    for i in range(12):
        metrics_data = []
        for metric_name, metric_config in service_config['metrics'].items():
            if metric_name == 'error_rate':
                value = random.uniform(8, 15)
            elif metric_name == 'p99_latency':
                value = random.uniform(1200, 2000)
            else:
                value = generate_metric_value(metric_config)

            metrics_data.append({
                'name': metric_name,
                'value': value,
                'type': 'gauge',
                'unit': metric_config.get('unit', '')
            })

        push_batch_metrics(service_name, service_config['token'], metrics_data)
        time.sleep(5)

    logger.info("\nAlert simulation complete. Check dashboard for alerts!")


def show_help():
    print("""
SRE Monitoring Dashboard - Mock Metric Pusher

Usage:
    python mock_push.py [options]

Options:
    --once              Push metrics once and exit (default: continuous)
    --batch             Use batch API (default)
    --individual        Use individual metric API
    --interval SECONDS  Push interval in seconds (default: 5)
    --duration SECONDS  Run for N seconds then exit
    --alert-sim         Simulate an alert scenario (high error rate)
    --help              Show this help message

Examples:
    python mock_push.py                    # Continuous push, batch mode, 5s interval
    python mock_push.py --once             # Push once
    python mock_push.py --interval 10      # Push every 10 seconds
    python mock_push.py --alert-sim        # Simulate error rate spike
    python mock_push.py --duration 60      # Run for 60 seconds
    """)


if __name__ == '__main__':
    use_batch = True
    interval = 5
    duration = None
    run_once = False
    alert_sim = False

    for arg in sys.argv[1:]:
        if arg in ['--help', '-h']:
            show_help()
            sys.exit(0)
        elif arg == '--once':
            run_once = True
        elif arg == '--batch':
            use_batch = True
        elif arg == '--individual':
            use_batch = False
        elif arg == '--alert-sim':
            alert_sim = True
        elif arg.startswith('--interval='):
            interval = int(arg.split('=')[1])
        elif arg.startswith('--duration='):
            duration = int(arg.split('=')[1])

    if alert_sim:
        simulate_alert_scenario()
    elif run_once:
        run_single_push(use_batch)
    else:
        run_continuous_push(interval, use_batch, duration)
