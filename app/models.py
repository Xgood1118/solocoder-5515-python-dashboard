from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    health_status = db.Column(db.String(20), default='healthy', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    metrics = db.relationship('Metric', backref='service', cascade='all, delete-orphan', lazy='dynamic')
    alerts = db.relationship('Alert', backref='service', cascade='all, delete-orphan', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'health_status': self.health_status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


class Metric(db.Model):
    __tablename__ = 'metrics'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True)
    metric_type = db.Column(db.String(20), nullable=False)
    unit = db.Column(db.String(20), default='')
    collect_interval = db.Column(db.Integer, default=60)
    retention_seconds = db.Column(db.Integer, default=Config.DEFAULT_SAMPLE_RETENTION)
    description = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint('service_id', 'name', name='_service_metric_uc'),)

    thresholds = db.relationship('Threshold', backref='metric', cascade='all, delete-orphan', lazy='dynamic')
    samples = db.relationship('MetricSample', backref='metric', cascade='all, delete-orphan', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'service_id': self.service_id,
            'service_name': self.service.name if self.service else '',
            'metric_type': self.metric_type,
            'unit': self.unit,
            'collect_interval': self.collect_interval,
            'retention_seconds': self.retention_seconds,
            'description': self.description,
            'thresholds': [t.to_dict() for t in self.thresholds],
            'created_at': self.created_at.isoformat(),
        }


class Threshold(db.Model):
    __tablename__ = 'thresholds'

    id = db.Column(db.Integer, primary_key=True)
    metric_id = db.Column(db.Integer, db.ForeignKey('metrics.id', ondelete='CASCADE'), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)
    threshold_value = db.Column(db.Float, nullable=False)
    duration_seconds = db.Column(db.Integer, default=60)
    level = db.Column(db.String(20), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'metric_id': self.metric_id,
            'direction': self.direction,
            'threshold_value': self.threshold_value,
            'duration_seconds': self.duration_seconds,
            'level': self.level,
            'channel': self.channel,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat(),
        }


class MetricSample(db.Model):
    __tablename__ = 'metric_samples'

    id = db.Column(db.Integer, primary_key=True)
    metric_id = db.Column(db.Integer, db.ForeignKey('metrics.id', ondelete='CASCADE'), nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.Index('idx_metric_timestamp', 'metric_id', 'timestamp'),)

    def to_dict(self):
        return {
            'metric_id': self.metric_id,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
        }

    @staticmethod
    def to_echarts_format(samples):
        if not samples:
            return {'x': [], 'y': []}
        x_data = []
        y_data = []
        for s in samples:
            x_data.append(s.timestamp.strftime('%Y-%m-%d %H:%M:%S'))
            y_data.append(s.value)
        return {'x': x_data, 'y': y_data}


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    metric_id = db.Column(db.Integer, db.ForeignKey('metrics.id', ondelete='CASCADE'), nullable=False, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True)
    threshold_id = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(20), default='OK', nullable=False, index=True)
    level = db.Column(db.String(20), nullable=False)
    current_value = db.Column(db.Float, nullable=False)
    threshold_value = db.Column(db.Float, nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    duration_seconds = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    last_notified_at = db.Column(db.DateTime, nullable=True)
    message = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (db.Index('idx_metric_state_level', 'metric_id', 'state', 'level'),)

    def to_dict(self):
        return {
            'id': self.id,
            'metric_id': self.metric_id,
            'service_id': self.service_id,
            'metric_name': self.metric.name if self.metric else '',
            'service_name': self.service.name if self.service else '',
            'state': self.state,
            'level': self.level,
            'current_value': self.current_value,
            'threshold_value': self.threshold_value,
            'direction': self.direction,
            'duration_seconds': self.duration_seconds,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'message': self.message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
