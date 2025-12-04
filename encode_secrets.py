import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 1) Encode client_secret.json
client_path = BASE_DIR / "gdrive_credentials" / "client_secret.json"
with client_path.open("rb") as f:
    raw = f.read()
print("CLIENT_SECRET_B64:")
print(base64.b64encode(raw).decode("ascii"))
print()

# 2) Encode service account json (optional but recommended)
service_path = BASE_DIR / "gdrive_credentials" / "linang-test-integration-key.json"
with service_path.open("rb") as f:
    raw = f.read()
print("SERVICE_ACCOUNT_B64:")
print(base64.b64encode(raw).decode("ascii"))
print()