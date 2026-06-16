from celery import Celery
from core.config import settings

broker = settings.celery_broker_url or settings.get_redis_url().replace("/0", "/1")
backend = settings.celery_result_backend or settings.get_redis_url().replace("/0", "/2")

celery_app = Celery(
    "claw_zep",
    broker=broker,
    backend=backend,
    include=[
        "core.tasks.graphiti_tasks",
        "core.tasks.memory_tree_tasks",
        "core.tasks.cleanup_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "core.tasks.graphiti_tasks.*": {"queue": "graphiti"},
        "core.tasks.memory_tree_tasks.*": {"queue": "memory_tree"},
        "core.tasks.cleanup_tasks.*": {"queue": "cleanup"},
    },
    beat_schedule={
        "memory-tree-global-summary": {
            "task": "core.tasks.memory_tree_tasks.build_global_summaries",
            "schedule": settings.memory_tree_global_summary_interval_hours * 3600,
        },
        "cleanup-expired-temporal-data": {
            "task": "core.tasks.cleanup_tasks.cleanup_expired_data",
            "schedule": 3600,  # every hour
        },
    },
)
