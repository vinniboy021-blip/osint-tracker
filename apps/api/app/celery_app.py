"""Celery transports work; PostgreSQL remains the source of truth for jobs."""

import os

from celery import Celery  # type: ignore[import-untyped]
from kombu import Queue  # type: ignore[import-untyped]

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
celery_app = Celery(
    "osint_tracker",
    broker=os.getenv("CELERY_BROKER_URL", redis_url),
    backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
    include=["app.collection", "app.monitoring"],
)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_soft_time_limit=150,
    task_time_limit=180,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=2,
    broker_transport_options={
        "visibility_timeout": 600,
        "priority_steps": [0, 3, 6, 9],
        "queue_order_strategy": "priority",
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
    },
    result_expires=3600,
    task_default_queue="collections",
    task_queues=(Queue("collections"), Queue("maintenance")),
    task_routes={"app.monitoring.sweep": {"queue": "maintenance"}},
    beat_schedule={
        "durable-monitor-and-job-sweep": {
            "task": "app.monitoring.sweep",
            "schedule": 15.0,
        }
    },
)
