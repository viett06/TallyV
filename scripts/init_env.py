"""Create local demo credentials without logging them."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
if path.exists():
    raise SystemExit(".env already exists; preserved")
db_password = secrets.token_hex(16)
password = "Demo-" + secrets.token_urlsafe(10)
path.write_text(
    f"SECRET_KEY={secrets.token_hex(32)}\nDEMO_USERNAME=hr.demo\nDEMO_PASSWORD={password}\n"
    f"POSTGRES_PASSWORD={db_password}\n"
    f"DATABASE_URL=postgresql+psycopg://tallyv:{db_password}@127.0.0.1:54329/tallyv\n"
    "PROCESSING_MODE=RULE_BASED\nOCR_ENABLED=true\n",
    encoding="utf-8",
)
path.chmod(0o600)
print("Created .env with generated demo credentials. Read locally to sign in.")
