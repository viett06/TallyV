"""Composio-managed OAuth and read-only Graph proxy calls for synthetic MVP mail."""

import hashlib
import hmac
import re

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.core.i18n import message
from app.services.outlook_provider import GraphError, graph_url

API_ROOT = "https://backend.composio.dev/api/v3.1"
MAX_RESPONSE_BYTES = 36 * 1024 * 1024
READ_SCOPES = "openid,profile,email,offline_access,User.Read,Mail.Read"


def require_mvp() -> None:
    if not settings.outlook_test_mode:
        raise AppError(403, message("composio.synthetic_only"))


def configured() -> bool:
    return bool(
        settings.composio_api_key.get_secret_value() and settings.composio_auth_config_id and settings.outlook_test_mode
    )


def user_id(owner_id: int) -> str:
    digest = hmac.new(settings.secret_key.encode(), f"composio:{owner_id}".encode(), hashlib.sha256).hexdigest()
    return "tallyv-" + digest


def account_id(value: str) -> str:
    if not re.fullmatch(r"ca_[A-Za-z0-9_-]{1,200}", value):
        raise ValueError("Invalid Composio connected account ID")
    return value


class ComposioClient:
    def __init__(self, *, client=None, api_key: str | None = None):
        self.client = client
        self.api_key = api_key if api_key is not None else settings.composio_api_key.get_secret_value()
        self.owns_client = client is None

    def __enter__(self):
        if self.client is None:
            self.client = httpx.Client(timeout=30, trust_env=False, follow_redirects=False)
        return self

    def __exit__(self, *_):
        if self.owns_client and self.client is not None:
            self.client.close()

    def request(self, method: str, path: str, *, body=None, missing_ok=False) -> dict:
        require_mvp()
        if not self.api_key:
            raise AppError(409, message("composio.configuration_required"))
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise ValueError("Composio API paths must be relative to the fixed API origin")
        with self.client.stream(method, API_ROOT + path, json=body, headers={"x-api-key": self.api_key}) as response:
            if response.status_code == 404 and missing_ok:
                return {}
            if response.status_code in {401, 403}:
                raise AppError(503, message("composio.invalid_key"))
            if response.status_code in {402, 429, 503}:
                error = AppError(503, message("composio.rate_limited"))
                retry = response.headers.get("Retry-After", "")
                error.retry_after = min(3600, max(1, int(retry))) if retry.isdigit() else 300
                raise error
            if response.status_code not in {200, 201, 204}:
                raise AppError(502, message("composio.service_unavailable"))
            if response.status_code == 204:
                return {}
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise AppError(502, message("outlook.message_too_large"))
                chunks.append(chunk)
        try:
            result = httpx.Response(200, content=b"".join(chunks)).json()
        except ValueError:
            raise AppError(502, message("composio.service_unavailable")) from None
        if not isinstance(result, dict):
            raise AppError(502, message("composio.service_unavailable"))
        return result

    def graph_json(self, connected_account: str, owner_id: int, url: str) -> dict:
        result = self.request(
            "POST",
            "/tools/execute/proxy",
            body={
                "connected_account_id": account_id(connected_account),
                "user_id": user_id(owner_id),
                "endpoint": graph_url(url),
                "method": "GET",
                "parameters": [
                    {
                        "name": "Prefer",
                        "value": 'IdType="ImmutableId", outlook.body-content-type="text", odata.maxpagesize=10',
                        "type": "header",
                    }
                ],
            },
        )
        status = result.get("status")
        if not isinstance(status, int):
            raise AppError(502, message("composio.service_unavailable"))
        if status != 200:
            headers = {key.lower(): str(value) for key, value in result.get("headers", {}).items()}
            raise GraphError(status, headers.get("retry-after", ""))
        if not isinstance(result.get("data"), dict) or result.get("binary_data"):
            # No token export, arbitrary file URLs, or downloads from signed storage URLs.
            raise AppError(502, message("composio.service_unavailable"))
        return result["data"]

    def get_account(self, connected_account: str) -> dict:
        return self.request("GET", "/connected_accounts/" + account_id(connected_account))

    def delete_account(self, connected_account: str) -> None:
        self.request(
            "DELETE", "/connected_accounts/" + account_id(connected_account) + "?revoke_on_delete=true", missing_ok=True
        )
