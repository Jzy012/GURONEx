import os
import json
import base64
from typing import Optional, Dict, Any

from django.conf import settings
from google.oauth2 import service_account


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _load_info_from_settings_or_env() -> Optional[Dict[str, Any]]:
    """
    Load service account JSON as a dict from, in order of precedence:
    1) settings.GOOGLE_SERVICE_ACCOUNT_INFO (dict or JSON string)
    2) GOOGLE_SERVICE_ACCOUNT_INFO env var (JSON string)
    3) GOOGLE_SERVICE_ACCOUNT_INFO_B64 env var (base64-encoded JSON)
    Returns a dict or None if not found.
    """
    # 1) From settings (may be dict if using environ's JSON parser, or a JSON string)
    info_from_settings = getattr(settings, "GOOGLE_SERVICE_ACCOUNT_INFO", None)
    if isinstance(info_from_settings, dict):
        return info_from_settings
    if isinstance(info_from_settings, str) and info_from_settings.strip():
        try:
            return json.loads(info_from_settings)
        except json.JSONDecodeError as e:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_INFO in settings is not valid JSON") from e

    # 2) Raw JSON string from env
    info_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO")
    if info_str:
        try:
            return json.loads(info_str)
        except json.JSONDecodeError as e:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_INFO env var is not valid JSON") from e

    # 3) Base64-encoded JSON from env
    info_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO_B64")
    if info_b64:
        try:
            decoded = base64.b64decode(info_b64).decode("utf-8")
            return json.loads(decoded)
        except Exception as e:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_INFO_B64 is not valid base64-encoded JSON") from e

    return None


def build_service_account_credentials(scopes=None):
    scopes = scopes or DRIVE_SCOPES

    # Preferred: JSON content (env/secret manager)
    info = _load_info_from_settings_or_env()
    if info:
        try:
            creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        except Exception as e:
            raise RuntimeError("Failed to build credentials from GOOGLE_SERVICE_ACCOUNT_INFO") from e
    else:
        # Fallback: file path (good for local dev; ensure it's gitignored)
        key_path = getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", None)
        if not key_path:
            raise FileNotFoundError(
                "Missing service account credentials. "
                "Set GOOGLE_SERVICE_ACCOUNT_INFO (preferred) or GOOGLE_SERVICE_ACCOUNT_FILE."
            )
        if not os.path.exists(key_path):
            raise FileNotFoundError(f"Service account file not found: {key_path}")
        try:
            creds = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
        except Exception as e:
            raise RuntimeError(f"Failed to build credentials from file: {key_path}") from e

    # Optional: Workspace domain-wide delegation impersonation
    subject = getattr(settings, "GOOGLE_IMPERSONATION_SUBJECT", None)
    if subject:
        creds = creds.with_subject(subject)

    return creds