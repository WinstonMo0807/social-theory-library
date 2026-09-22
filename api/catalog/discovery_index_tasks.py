"""Serialized CPU indexing queue, separate from upload and reader query workers."""
from celery import shared_task


@shared_task(bind=True, name="catalog.tasks.process_discovery_index_job", soft_time_limit=600, time_limit=660)
def process_discovery_index_job(self, job_id):
    from catalog.services.discovery_indexing import run_job
    return run_job(job_id, str(self.request.id or ""))


@shared_task(name="catalog.tasks.reconcile_discovery_index", soft_time_limit=240, time_limit=270)
def reconcile_discovery_index():
    from catalog.services.discovery_indexing import reconcile
    return reconcile()
