from celery import shared_task
from . import email_links


@shared_task(ignore_result=True, soft_time_limit=45, time_limit=60, acks_late=False)
def deliver_account_link(encrypted_request):
    # Celery sees an encrypted request, never the email address or bearer link.
    email_links.deliver(encrypted_request)
