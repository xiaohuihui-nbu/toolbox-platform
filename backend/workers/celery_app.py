from celery import Celery

from app.toolbox.config import settings

celery = Celery("toolbox", broker=settings().redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=False,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 1200},
    task_default_queue="toolbox",
    worker_max_tasks_per_child=30,
    task_time_limit=900,
    task_soft_time_limit=870,
)


celery.conf.imports = ("workers.tasks", "app.toolbox.jobs.capabilities")
