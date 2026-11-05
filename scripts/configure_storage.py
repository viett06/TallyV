"""Generate MinIO credentials in .env, preserving other settings and existing secrets."""

import argparse
import re
import secrets
from pathlib import Path


def configure(path: Path, activate: bool = False):
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    values = {}
    for line in content.splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if match:
            values[match[1]] = match[2].strip().strip("\"'")
    defaults = {
        "STORAGE_BACKEND": "local",
        "S3_ENDPOINT_URL": "http://127.0.0.1:9000",
        "S3_DOCKER_ENDPOINT_URL": "http://minio:9000",
        "S3_REGION": "us-east-1",
        "S3_BUCKET": "tallyv-files",
        "S3_PREFIX": "tallyv/",
        "S3_ADDRESSING_STYLE": "path",
        "MINIO_ROOT_USER": "tallyv-admin-" + secrets.token_hex(4),
        "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(32),
        "S3_ACCESS_KEY_ID": "tallyv-app-" + secrets.token_hex(4),
        "S3_SECRET_ACCESS_KEY": secrets.token_urlsafe(32),
    }
    if activate:
        defaults["STORAGE_BACKEND"] = "s3"
    for key, value in defaults.items():
        if values.get(key) and not (key == "STORAGE_BACKEND" and activate):
            continue
        replacement = f"{key}={value}"
        if re.search(rf"^{key}=.*$", content, flags=re.MULTILINE):
            content = re.sub(rf"^{key}=.*$", replacement, content, flags=re.MULTILINE)
        else:
            content = content.rstrip("\n") + "\n" + replacement + "\n"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate", action="store_true", help="Switch writes/reads to S3 after migration")
    args = parser.parse_args()
    configure(Path(__file__).resolve().parents[1] / ".env", args.activate)
    print("Storage configuration saved in .env; credentials were not printed. Restart API/worker after activation.")
