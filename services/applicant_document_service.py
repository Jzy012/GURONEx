# services/applicant_document_service.py

import io
from googleapiclient.http import MediaIoBaseUpload

from applicant.models import Applicant, ApplicantDocument
from services.google_drive_service import CentralGoogleDriveService


def process_applicant_documents_sync(applicant_id, docs_payload):
    """
    Upload registration documents to Google Drive and update the ApplicantDocument
    stub records (already created in the view's atomic block) with Drive URLs.

    docs_payload items must include "stub_id" pointing to an existing
    ApplicantDocument pk. If stub_id is absent, a new record is created
    (backwards-compatible fallback).
    """
    applicant = Applicant.objects.get(id=applicant_id)
    drive_service = CentralGoogleDriveService()

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
                body={"name": doc["name"], "parents": [folder_id]},
                media_body=media,
                fields="id,webViewLink",
            )
            .execute()
        )

        stub_id = doc.get("stub_id")
        if stub_id:
            ApplicantDocument.objects.filter(pk=stub_id).update(
                file_path=upload["webViewLink"],
                google_drive_id=upload["id"],
            )
        else:
            ApplicantDocument.objects.create(
                applicant=applicant,
                document_category_id=doc["document_category_id"],
                file_path=upload["webViewLink"],
                google_drive_id=upload["id"],
                file_size=doc["size"],
                expiry_date=doc["expiry_date"],
                remarks=doc.get("remarks", ""),
                status="Pending",
            )