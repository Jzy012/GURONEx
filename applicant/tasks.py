# applicants/tasks.py

from celery import shared_task

from services.applicant_document_service import process_applicant_documents_sync


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_applicant_documents_task(self, applicant_id, docs_payload):
    """
    Celery task to process applicant documents asynchronously.

    It just calls the existing synchronous helper.
    """
    try:
        process_applicant_documents_sync(applicant_id, docs_payload)
    except Exception as exc:
        # Optional: log or add custom retry logic
        raise self.retry(exc=exc)