import json
from googleapiclient.discovery import build
from django.conf import settings
from django.utils.timezone import now
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
        folder_path = f"FEMS/Faculty/{faculty_profile.name.strip().replace('/', '_').replace('\\', '_')}"
        return self.get_or_create_folder_path(folder_path)

    def create_applicant_folder(self, applicant):
        folder_name = f"{applicant.applicant_id} - {applicant.first_name} {applicant.last_name}{' ' + applicant.suffix if applicant.suffix else ''}".strip()
        folder_path = f"FEMS/Applicants/{folder_name}"
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
    


    def delete_file(self, file_id):
        """
        Permanently delete a file from Google Drive by its file ID.
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
        except Exception as e:
            # Log but don't break the user flow
            print(f"[Drive] Failed to delete file {file_id}: {e}")