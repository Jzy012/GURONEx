"""
Photo documentation upload for faculty manual attendance logs.

Reuses the same Google Drive storage the rest of the document system uses
(CentralGoogleDriveService). The application's local MEDIA_ROOT is not durable
on this deployment, so evidence attached to an attendance record must not live
there.
"""

import io
import logging
import os
import re

from django.utils import timezone
from googleapiclient.http import MediaIoBaseUpload

from services.google_drive_service import CentralGoogleDriveService

logger = logging.getLogger(__name__)

DOCUMENTATION_FOLDER_NAME = "Attendance Documentation"

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class AttendanceDocumentationError(Exception):
    """Raised when the photo documentation could not be stored."""


def _build_filename(faculty, attendance_date, original_name):
    """
    Deterministic, sanitized filename so uploads are identifiable in Drive and
    the user-supplied name can never influence the stored path.
    """
    ext = os.path.splitext(original_name or "")[1].lower().lstrip(".") or "jpg"
    ext = _UNSAFE_FILENAME_CHARS.sub("", ext) or "jpg"

    identifier = getattr(faculty, "faculty_code", None) or getattr(faculty, "pk", "unknown")
    identifier = _UNSAFE_FILENAME_CHARS.sub("_", str(identifier))

    stamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    return f"attendance_{identifier}_{attendance_date:%Y%m%d}_{stamp}.{ext}"


def upload_attendance_documentation(faculty, attendance_date, photo):
    """
    Upload photo documentation for a manual attendance log.

    Returns (webViewLink, drive_file_id). Raises AttendanceDocumentationError if
    the file could not be stored, so the caller can reject the submission rather
    than saving an attendance record whose required evidence is missing.
    """
    try:
        service = CentralGoogleDriveService()

        parent_id = getattr(faculty, "gdrive_folder_id", None)
        if not parent_id:
            parent_id = service.create_faculty_folder(faculty)

        folder_id = service.get_or_create_named_folder(
            DOCUMENTATION_FOLDER_NAME,
            parent_id=parent_id,
        )

        photo.seek(0)
        media = MediaIoBaseUpload(
            io.BytesIO(photo.read()),
            mimetype=getattr(photo, "content_type", None) or "image/jpeg",
            resumable=False,
        )

        upload = service.service.files().create(
            body={
                "name": _build_filename(faculty, attendance_date, photo.name),
                "parents": [folder_id],
            },
            media_body=media,
            fields="id,webViewLink",
        ).execute()

        return upload.get("webViewLink", ""), upload.get("id", "")

    except Exception as exc:
        logger.exception(
            "Failed to upload attendance documentation for faculty %s on %s",
            getattr(faculty, "pk", None),
            attendance_date,
        )
        raise AttendanceDocumentationError(
            "Photo documentation could not be uploaded. Please try again."
        ) from exc
