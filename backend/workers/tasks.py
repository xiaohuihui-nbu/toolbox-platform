from app.toolbox.jobs.execution import run_job
from app.toolbox.search.videos import execute_search
from workers.celery_app import celery


@celery.task(name="toolbox.execute")
def execute(job_id, attempt_id=None):
    return run_job(job_id, attempt_id)


@celery.task(name="toolbox.video_search", time_limit=70, soft_time_limit=65)
def search_videos(search_id):
    return execute_search(search_id)
