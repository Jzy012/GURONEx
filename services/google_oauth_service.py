import json
from google_auth_oauthlib.flow import Flow
from django.conf import settings
from base.models import GoogleStorageAccount

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

def load_client_secrets():
    from django.conf import settings

    with open(settings.GOOGLE_CLIENT_SECRET_FILE, 'r') as f:
        raw = f.read()
    print("DEBUG client_secret.json content:", repr(raw))  # TEMP

    secrets = json.loads(raw)
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
            prompt='consent'
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

        # Save centrally! Deactivate old accounts.
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        token_info = id_token.verify_oauth2_token(
            creds.id_token, google_requests.Request(), audience=creds.client_id
        )
        email = token_info.get("email")

        # Check that all required fields are present
        if not creds.token or not creds.refresh_token or not creds.expiry:
            raise ValueError("Missing required credential data (access_token, refresh_token, or expiry).")

        # Deactivate all other accounts
        GoogleStorageAccount.objects.exclude(email=email).update(is_active=False)

        # Use defaults to ensure NOT NULL columns are set on creation
        account, created = GoogleStorageAccount.objects.get_or_create(
            email=email,
            defaults={
                'access_token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_expiry': creds.expiry,
                'is_active': True,
            }
        )
        if not created:
            # Update all fields if the account already exists
            account.access_token = creds.token
            account.refresh_token = creds.refresh_token
            account.token_expiry = creds.expiry
            account.is_active = True
            account.save()

        return creds