# services/applicant_document_service.py

import io
from googleapiclient.http import MediaIoBaseUpload

from applicant.models import Applicant, ApplicantDocument
from services.google_drive_service import CentralGoogleDriveService


def process_applicant_documents_sync(applicant_id, docs_payload):
    """
    Synchronous processing of applicant documents.

    docs_payload: list of dicts:
    [
      {
        "name": "filename.pdf",
        "content": bytes,
        "content_type": "application/pdf",
        "size": 12345,
        "document_category_id": 1,
        "expiry_date": date or None,
        "remarks": "",
      },
      ...
    ]
    """
    applicant = Applicant.objects.get(id=applicant_id)
    drive_service = CentralGoogleDriveService()

    # Ensure applicant Drive folder exists (using your existing method)
    if not applicant.google_drive_folder_id:
        folder_id = drive_service.create_applicant_folder(applicant)
        applicant.google_drive_folder_id = folder_id
        applicant.save(update_fields=["google_drive_folder_id"])
    else:
        folder_id = applicant.google_drive_folder_id

    for doc in docs_payload:
        file_bytes = doc["content"]

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=doc["content_type"],
            resumable=False,
        )

        upload = (
            drive_service.service.files()
            .create(
                body={
                    "name": doc["name"],
                    "parents": [folder_id],
                },
                media_body=media,
                fields="id,webViewLink",
            )
            .execute()
        )

        ApplicantDocument.objects.create(
            applicant=applicant,
            document_category_id=doc["document_category_id"],
            file_path=upload["webViewLink"],
            google_drive_id=upload["id"],
            file_size=doc["size"],
            expiry_date=doc["expiry_date"],
            remarks=doc["remarks"],
            status="Pending",
        )