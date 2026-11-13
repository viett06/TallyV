"""Private file storage for imports, downloads and processed evidence (local or S3-compatible)."""

import base64
import hashlib
import re
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message


def validate_name(name: str) -> str:
    # DB references are opaque UUID names, never URLs, paths or employee identities.
    if not re.fullmatch(r"[0-9a-f]{32}\.(?:bin|png|jpg|jpeg|xlsx)", name):
        raise ValueError("Invalid stored file name")
    return name


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, name: str) -> Path:
        target = (self.root / validate_name(name)).resolve()
        if target.parent != self.root:
            raise ValueError("Invalid stored file path")
        return target

    def read(self, name: str) -> bytes:
        return self.path(name).read_bytes()

    def write(self, name: str, content: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path(name).write_bytes(content)

    def delete(self, name: str) -> None:
        self.path(name).unlink(missing_ok=True)


class S3Storage:
    def __init__(self, client, bucket: str, prefix: str):
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def key(self, name: str) -> str:
        return self.prefix + validate_name(name)

    def read(self, name: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self.key(name))
        with response["Body"] as body:
            content = body.read()
        expected = response.get("Metadata", {}).get("sha256")
        if expected and hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Stored object checksum mismatch")
        return content

    def write(self, name: str, content: bytes) -> None:
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }.get(Path(name).suffix, "application/octet-stream")
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.key(name),
            Body=content,
            ContentType=content_type,
            ContentMD5=base64.b64encode(hashlib.md5(content, usedforsecurity=False).digest()).decode(),
            Metadata={"sha256": hashlib.sha256(content).hexdigest()},
        )

    def delete(self, name: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self.key(name))


@lru_cache(maxsize=4)
def _s3_client(endpoint: str, region: str, access_key: str, secret_key: str, addressing_style: str):
    credentials = {"aws_access_key_id": access_key, "aws_secret_access_key": secret_key} if access_key else {}
    return boto3.session.Session().client(
        "s3",
        endpoint_url=endpoint or None,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": addressing_style},
            connect_timeout=3,
            read_timeout=30,
            retries={"mode": "standard", "max_attempts": 3},
        ),
        **credentials,
    )


def get_storage() -> LocalStorage | S3Storage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_dir)
    return get_s3_storage()


def get_s3_storage() -> S3Storage:
    return S3Storage(
        _s3_client(
            settings.s3_endpoint_url,
            settings.s3_region,
            settings.s3_access_key_id.get_secret_value(),
            settings.s3_secret_access_key.get_secret_value(),
            settings.s3_addressing_style,
        ),
        settings.s3_bucket,
        settings.s3_prefix,
    )


def store_bytes(content: bytes, suffix: str) -> tuple[str, str]:
    name = validate_name(f"{uuid4().hex}{suffix}")
    try:
        get_storage().write(name, content)
    except (BotoCoreError, ClientError, OSError) as error:
        raise AppError(503, message("storage.unavailable")) from error
    return name, hashlib.sha256(content).hexdigest()


def read_bytes(name: str) -> bytes:
    validate_name(name)
    try:
        return get_storage().read(name)
    except FileNotFoundError as error:
        raise AppError(404, message("storage.not_found")) from error
    except ClientError as error:
        status = 404 if error.response["Error"]["Code"] in {"NoSuchKey", "404", "NotFound"} else 503
        raise AppError(status, message("storage.not_found" if status == 404 else "storage.unavailable")) from error
    except (BotoCoreError, OSError, ValueError) as error:
        raise AppError(503, message("storage.unavailable")) from error


def delete_file(name: str) -> None:
    get_storage().delete(validate_name(name))
