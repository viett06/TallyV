"""Configure the synthetic Outlook MVP using a hidden, local Composio project key."""

import getpass
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import httpx

from app.core.config import ROOT
from app.core.errors import AppError
from app.services.composio_client import READ_SCOPES, ComposioClient


def save_environment(path: Path, values: dict[str, str]) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to replace a symbolic-link environment file")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines, written = [], set()
    for line in existing.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=", line)
        key = match[1] if match else None
        if key in values:
            if key not in written:
                lines.append(f"{key}={json.dumps(values[key])}")
                written.add(key)
        else:
            lines.append(line)
    lines.extend(f"{key}={json.dumps(value)}" for key, value in values.items() if key not in written)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".env.composio-", delete=False
        ) as output:
            temporary = Path(output.name)
            os.chmod(temporary, 0o600)
            output.write("\n".join(lines) + "\n")
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def configure(api_key: str, *, path: Path = ROOT / ".env", client=None) -> None:
    if not api_key or any(character in api_key for character in "\r\n"):
        raise ValueError("Enter a nonempty, single-line Composio project API key")
    with ComposioClient(api_key=api_key, client=client) as api:
        result = api.request(
            "POST",
            "/auth_configs",
            body={
                "toolkit": {"slug": "outlook"},
                "auth_config": {
                    "type": "use_composio_managed_auth",
                    "name": "TallyV synthetic MVP - read only",
                    "credentials": {"scopes": READ_SCOPES},
                },
            },
        )
    config = result.get("auth_config") or {}
    if (
        result.get("toolkit", {}).get("slug") != "outlook"
        or not config.get("is_composio_managed")
        or not re.fullmatch(r"ac_[A-Za-z0-9_-]{1,200}", config.get("id", ""))
    ):
        raise ValueError("Composio did not return an Outlook managed auth configuration")
    save_environment(
        path,
        {
            "MAIL_PROVIDER": "outlook",
            "OUTLOOK_TRANSPORT": "composio",
            "OUTLOOK_TEST_MODE": "true",
            "COMPOSIO_API_KEY": api_key,
            "COMPOSIO_AUTH_CONFIG_ID": config["id"],
            "COMPOSIO_POLL_INTERVAL": "0",
        },
    )


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run this setup in an interactive terminal; never pass API keys on the command line")
    print("Use a free Composio project at https://dashboard.composio.dev.")
    print("Copy its project API key. Entry below is hidden; do not paste the key into chat.")
    print("This setup creates an Outlook managed OAuth configuration for synthetic data only.")
    key = getpass.getpass("Composio project API key: ").strip()
    try:
        configure(key)
    except (AppError, ValueError, httpx.HTTPError):
        raise SystemExit("Setup failed; .env was not updated. Check the key, network, and Composio project.") from None
    print("Configured Composio in .env without changing existing application/database secrets.")
    print("Docker API and worker: docker compose -f compose.yaml -f compose.outlook.yaml up -d api worker")
    print("If Uvicorn runs locally, restart it and recreate only the worker:")
    print("docker compose -f compose.yaml -f compose.outlook.yaml up -d --no-deps worker")
    print("Use 'up -d', not just 'restart': existing containers keep their old environment until recreated.")
    print("Then choose Connect Outlook in TallyV.")


if __name__ == "__main__":
    main()
