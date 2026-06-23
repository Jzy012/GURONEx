import json
from googleapiclient.discovery import build
from django.conf import settings
from django.urls import reverse
from django.utils.timezone import now
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from base.models import GoogleStorageAccount

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

def load_client_secrets():
    with open(settings.GOOGLE_CLIENT_SECRET_FILE, 'r') as f:
        secrets = json.load(f)
        return secrets.get("installed") or secrets.get("web")

class CentralGoogleDriveService:
    def __init__(self):
        # --- Only use the global GoogleStorageAccount ---
        self.account = GoogleStorageAccount.objects.filter(is_active=True).first()
        if not self.account:
            raise Exception("No active Google Drive storage account found. Please connect Google Drive in admin.")

        client_secrets = load_client_secrets()
        self.client_id = client_secrets["client_id"]
        self.client_secret = client_secrets["client_secret"]
        self.creds = self._get_or_refresh_credentials()
        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)

    def _get_or_refresh_credentials(self):
        creds = Credentials(
            token=self.account.access_token,
            refresh_token=self.account.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=SCOPES
        )
        # --- Always refresh if expired ---
        if self.account.token_expiry <= now():
            creds.refresh(GoogleRequest())
            self.account.access_token = creds.token
            self.account.token_expiry = creds.expiry
            self.account.save()
        return creds

    # --- All Google Drive actions below use central account ---

    def create_folder(self, name, parent_id=None):
        metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
        }
        if parent_id:
            metadata['parents'] = [parent_id]
        folder = self.service.files().create(body=metadata, fields='id').execute()
        return folder['id']

    def get_or_create_named_folder(self, name, parent_id=None):
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        else:
            query += " and 'root' in parents"
        files = self.service.files().list(q=query, fields="files(id)").execute().get("files", [])
        if files:
            return files[0]["id"]
        return self.create_folder(name, parent_id)

    def get_or_create_folder_path(self, path):
        parts = path.strip("/").split("/")
        parent_id = None
        for part in parts:
            parent_id = self.get_or_create_named_folder(part, parent_id=parent_id)
        return parent_id

    def create_faculty_folder(self, faculty_profile):
        folder_path = f"GURONEx/Faculty/{faculty_profile.name.strip().replace('/', '_').replace('\\', '_')}"
        return self.get_or_create_folder_path(folder_path)

    def create_applicant_folder(self, applicant):
        folder_name = f"{applicant.applicant_id} - {applicant.first_name} {applicant.last_name}{' ' + applicant.suffix if applicant.suffix else ''}".strip()
        folder_path = f"GURONEx/Applicants/{folder_name}"
        return self.get_or_create_folder_path(folder_path)

    def share_folder_with_user(self, folder_id, user_email, role="writer"):
        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': user_email
        }
        return self.service.permissions().create(
            fileId=folder_id,
            body=permission,
            sendNotificationEmail=True
        ).execute()
    
    def copy_file_to_folder(self, file_id, destination_folder_id, new_name=None):
        body = {
            'parents': [destination_folder_id]
        }
        if new_name:
            body['name'] = new_name
        new_file = self.service.files().copy(
            fileId=file_id,
            body=body,
            fields='id, webViewLink'
        ).execute()
        return new_file['id'], new_file.get('webViewLink')
    


    def move_file_to_folder(self, file_id, from_folder_id, to_folder_id, new_name=None):
        """
        Reassign a file's parent folder without copying — file ID and webViewLink stay the same.
        Falls back to copy+delete if from_folder_id is unavailable.
        """
        body = {}
        if new_name:
            body['name'] = new_name
        updated = self.service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=from_folder_id or '',
            body=body,
            fields='id, webViewLink',
        ).execute()
        return updated['id'], updated.get('webViewLink')

    def delete_file(self, file_id):
        """
        Permanently delete a file from Google Drive by its file ID.
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
        except Exception as e:
            # Log but don't break the user flow
            print(f"[Drive] Failed to delete file {file_id}: {e}")


def get_google_drive_status():
    account = GoogleStorageAccount.objects.filter(is_active=True).first()
    change_account_url = reverse("authorize_google")

    def _format_bytes(num_bytes):
        if num_bytes is None:
            return "Unknown"
        size = float(num_bytes)
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.2f} {unit}"
            size /= 1024

    def _attach_storage_quota(status_payload):
        status_payload.update({
            "storage_quota_available": False,
            "storage_usage_percent": None,
            "storage_used_human": None,
            "storage_limit_human": None,
            "storage_available_human": None,
            "storage_error": None,
        })

        try:
            drive = CentralGoogleDriveService()
            about = drive.service.about().get(fields="storageQuota").execute()
            quota = about.get("storageQuota", {})

            used = int(quota.get("usage") or 0)
            limit_raw = quota.get("limit")
            limit = int(limit_raw) if limit_raw else 0

            if limit > 0:
                usage_percent = round((used / limit) * 100, 2)
                usage_percent = max(0, min(100, usage_percent))
                available = max(limit - used, 0)
                status_payload.update({
                    "storage_quota_available": True,
                    "storage_usage_percent": usage_percent,
                    "storage_used_human": _format_bytes(used),
                    "storage_limit_human": _format_bytes(limit),
                    "storage_available_human": _format_bytes(available),
                })
                return

            status_payload.update({
                "storage_used_human": _format_bytes(used),
                "storage_limit_human": "Unknown",
                "storage_available_human": "Unknown",
                "storage_error": "Storage quota limit is unavailable for this account.",
            })
        except Exception:
            status_payload.update({
                "storage_error": "Could not fetch storage quota from Google Drive.",
            })

    if not account:
        return {
            "label": "Disconnected",
            "message": "No active Google Drive account.",
            "color_class": "bg-red-100 text-red-800",
            "reauth_url": change_account_url,
            "change_account_url": change_account_url,
            "account_email": None,
            "needs_reauth": True,
            "is_connected": False,
            "storage_quota_available": False,
            "storage_usage_percent": None,
            "storage_used_human": None,
            "storage_limit_human": None,
            "storage_available_human": None,
            "storage_error": None,
        }

    is_token_valid = bool(account.token_expiry and account.token_expiry > timezone.now())
    has_refresh_token = bool(getattr(account, "_refresh_token", None))

    if is_token_valid:
        status_payload = {
            "label": "Connected",
            "message": f"Active account: {account.email}",
            "color_class": "bg-green-100 text-green-800",
            "reauth_url": None,
            "change_account_url": change_account_url,
            "account_email": account.email,
            "needs_reauth": False,
            "is_connected": True,
        }
        _attach_storage_quota(status_payload)
        return status_payload

    if has_refresh_token:
        status_payload = {
            "label": "Connected",
            "message": "Access token expired, but refresh token is valid. It will auto-refresh when needed.",
            "color_class": "bg-green-100 text-green-800",
            "reauth_url": None,
            "change_account_url": change_account_url,
            "account_email": account.email,
            "needs_reauth": False,
            "is_connected": True,
        }
        _attach_storage_quota(status_payload)
        return status_payload

    return {
        "label": "Expired",
        "message": "Token expired and cannot be refreshed. Re-authentication required.",
        "color_class": "bg-red-100 text-red-800",
        "reauth_url": change_account_url,
        "change_account_url": change_account_url,
        "account_email": account.email,
        "needs_reauth": True,
        "is_connected": False,
        "storage_quota_available": False,
        "storage_usage_percent": None,
        "storage_used_human": None,
        "storage_limit_human": None,
        "storage_available_human": None,
        "storage_error": None,
    }