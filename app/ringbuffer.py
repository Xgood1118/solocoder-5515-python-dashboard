import threading
from collections import deque
from datetime import datetime, timedelta
from config import Config


class RingBuffer:
    def __init__(self, capacity=None, duration=None):
        self.capacity = capacity or Config.RINGBUFFER_CAPACITY
        self.duration = duration or Config.RINGBUFFER_DURATION
        self._buffer = deque(maxlen=self.capacity)
        self._lock = threading.Lock()

    def append(self, value, timestamp=None):
        if timestamp is None:
            timestamp = datetime.utcnow()
        with self._lock:
            self._buffer.append((timestamp, value))
            self._evict_expired()

    def _evict_expired(self):
        cutoff = datetime.utcnow() - timedelta(seconds=self.duration)
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def get_all(self):
        with self._lock:
            self._evict_expired()
            return list(self._buffer)

    def get_recent(self, seconds):
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        with self._lock:
            self._evict_expired()
            return [(ts, val) for ts, val in self._buffer if ts >= cutoff]

    def get_latest(self):
        with self._lock:
            self._evict_expired()
            if self._buffer:
                return self._buffer[-1]
            return None

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def __len__(self):
        with self._lock:
            self._evict_expired()
            return len(self._buffer)


class MetricBufferManager:
    def __init__(self):
        self._buffers = {}
        self._lock = threading.Lock()
        self._pending_samples = []
        self._pending_lock = threading.Lock()

    def _get_or_create_buffer(self, metric_id):
        if metric_id not in self._buffers:
            self._buffers[metric_id] = RingBuffer()
        return self._buffers[metric_id]

    def add_sample(self, metric_id, value, timestamp=None):
        if timestamp is None:
            timestamp = datetime.utcnow()
        buffer = self._get_or_create_buffer(metric_id)
        buffer.append(value, timestamp)
        with self._pending_lock:
            self._pending_samples.append({
                'metric_id': metric_id,
                'value': value,
                'timestamp': timestamp,
            })

    def get_metric_data(self, metric_id, seconds=None):
        with self._lock:
            if metric_id not in self._buffers:
                return []
            buffer = self._buffers[metric_id]
            if seconds:
                return buffer.get_recent(seconds)
            return buffer.get_all()

    def get_latest_value(self, metric_id):
        with self._lock:
            if metric_id not in self._buffers:
                return None
            latest = self._buffers[metric_id].get_latest()
            return latest[1] if latest else None

    def get_latest_with_time(self, metric_id):
        with self._lock:
            if metric_id not in self._buffers:
                return None
            return self._buffers[metric_id].get_latest()

    def drain_pending_samples(self):
        with self._pending_lock:
            samples = self._pending_samples[:]
            self._pending_samples.clear()
            return samples

    def get_all_metric_ids(self):
        with self._lock:
            return list(self._buffers.keys())

    def clear_metric(self, metric_id):
        with self._lock:
            if metric_id in self._buffers:
                self._buffers[metric_id].clear()
                del self._buffers[metric_id]

    def clear_all(self):
        with self._lock:
            self._buffers.clear()
        with self._pending_lock:
            self._pending_samples.clear()


buffer_manager = MetricBufferManager()
