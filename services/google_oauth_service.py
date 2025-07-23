import json
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from django.utils.timezone import now
from django.conf import settings

from base.models import GoogleDriveToken  # replace with your actual app name

SCOPES = ['https://www.googleapis.com/auth/drive',
          'openid',
          'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/userinfo.profile',
          ]

def load_client_secrets():
    with open(settings.GOOGLE_CLIENT_SECRET_FILE, 'r') as f:
        secrets = json.load(f)
        # Accept either "installed" or "web" as key for the client secrets
        if "installed" in secrets:
            return secrets["installed"]
        elif "web" in secrets:
            return secrets["web"]
        else:
            raise KeyError("Neither 'installed' nor 'web' found in client secret JSON file.")

class GoogleOAuthService:
    def __init__(self, user):
        self.user = user
        self.client_secrets = load_client_secrets()

        if not all(k in self.client_secrets for k in ['client_id', 'client_secret']):
            raise ValueError("Missing client_id or client_secret in client_secret.json")

    def get_auth_url(self):
        flow = Flow.from_client_secrets_file(
            settings.GOOGLE_CLIENT_SECRET_FILE,
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_OAUTH2_REDIRECT_URI
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent'  # forces refresh token every time
        )
        return auth_url

    def exchange_code_for_token(self, code):
        flow = Flow.from_client_secrets_file(
            settings.GOOGLE_CLIENT_SECRET_FILE,
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_OAUTH2_REDIRECT_URI
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        token_obj, created = GoogleDriveToken.objects.get_or_create(
            user=self.user,
            defaults={
                'access_token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_expiry': creds.expiry,
            }
        )
        if not created:
            token_obj.access_token = creds.token
            token_obj.refresh_token = creds.refresh_token
            token_obj.token_expiry = creds.expiry
            token_obj.save()


        return creds
    

    def get_credentials(self):
        try:
            token_obj = GoogleDriveToken.objects.get(user=self.user)
        except GoogleDriveToken.DoesNotExist:
            return None
        # If token expired, refresh it
        if token_obj.token_expiry <= now():
            creds = Credentials(
                token=token_obj.access_token,
                refresh_token=token_obj.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_secrets['client_id'],
                client_secret=self.client_secrets['client_secret'],
                scopes=SCOPES
            )
            creds.refresh(GoogleRequest())

            token_obj.access_token = creds.token
            token_obj.token_expiry = creds.expiry
            token_obj.save()

        # Return up-to-date credentials
        return Credentials(
            token=token_obj.access_token,
            refresh_token=token_obj.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_secrets['client_id'],
            client_secret=self.client_secrets['client_secret'],
            scopes=SCOPES
        )