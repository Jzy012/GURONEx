from googleapiclient.discovery import build
from django.conf import settings
from faculty.models import FacultyProfile
from services.google_oauth_service import GoogleOAuthService

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from django.utils.timezone import now
from base.models import GoogleStorageAccount

import json


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
        self.account = GoogleStorageAccount.objects.get(is_active=True)
        client_secrets = load_client_secrets()
        self.client_id = client_secrets["client_id"]
        self.client_secret = client_secrets["client_secret"]
        self.creds = self._get_or_refresh_credentials()
        self.service = build("drive", "v3", credentials=self.creds)

    def _get_or_refresh_credentials(self):
        creds = Credentials(
            token=self.account.access_token,
            refresh_token=self.account.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=SCOPES
        )

        if self.account.token_expiry <= now():
            creds.refresh(GoogleRequest())
            self.account.access_token = creds.token
            self.account.token_expiry = creds.expiry
            self.account.save()

        return creds

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

    def create_faculty_folder(self, faculty_profile):
        fems_root = self.get_or_create_named_folder("FEMS")
        faculty_root = self.get_or_create_named_folder("Faculty", parent_id=fems_root)

        clean_name = faculty_profile.name.strip().replace("/", "_").replace("\\", "_")
        folder_id = self.get_or_create_named_folder(clean_name, parent_id=faculty_root)

        return folder_id

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
