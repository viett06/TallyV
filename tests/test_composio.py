"""Exercise Composio auth and real workbook parsing against a deterministic HTTP boundary."""

import base64
import importlib.util
import json
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from openpyxl import load_workbook
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select, text

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.i18n import message
from app.core.time import utcnow
from app.models import Attachment, AttendanceCase, Email, OutlookAuthFlow, OutlookConnection, ProcessingJob
from app.services import composio_auth, composio_provider, mailbox, mailbox_auth
from app.services.composio_client import API_ROOT, READ_SCOPES, ComposioClient, user_id
from app.services.imports import process_email
from scripts.configure_composio import configure
from tests.test_outlook import configure_real_catalog, mime_message

REMOTE_ID = "ca_test_account"
AUTH_CONFIG = "ac_read_only_test"
SUBJECT = "[TALLYV-MVP] [DCC] [2026-11] [WEEK:2026-10-31] Synthetic department summary"
CHECKPOINT = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=complete"


def test_hr_can_rescan_a_window_and_monitor_real_intake_without_duplicates(composio, backend, monkeypatch):
    from app import worker

    sessions, client = composio
    configure_real_catalog(client)
    with sessions() as db:
        connect(db, backend)
        db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "SYNC")).status = "DONE"
        db.get(OutlookConnection, 1).delta_link = CHECKPOINT
        db.commit()
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    for days in (0, 366):
        assert client.post("/api/sync", json={"mode": "rescan", "lookback_days": days}).status_code == 422
    assert client.post("/api/sync", json={"mode": "all"}).status_code == 422
    first = client.post("/api/sync", json={"mode": "rescan", "lookback_days": 30})
    assert first.status_code == 200 and first.json()["status"] == "PENDING"
    assert worker.run_one()
    status = client.get("/api/outlook").json()
    assert status["status"] == "CONNECTED" and status["sync_status"] == "DONE"
    assert status["sync_summary"] == {"scanned": 4, "matched": 1, "new": 1, "existing": 0}
    delta_calls = [
        json.loads(request.content)["endpoint"]
        for request in backend["requests"]
        if request.url.path.endswith("/proxy") and "/delta?" in json.loads(request.content)["endpoint"]
    ]
    initial = parse_qs(urlsplit(delta_calls[0]).query)
    assert initial["$filter"][0].startswith(
        "receivedDateTime ge " + (utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    )
    assert worker.run_one()  # Import Excel before the separate analysis action.
    assert not worker.run_one()
    imported = client.get("/api/cases", params={"source": "outlook"}).json()["items"][0]
    assert imported["analysis"]["status"] == "NOT_STARTED"
    assert client.post("/api/analysis?source=outlook").json() == {"queued": 1}
    assert worker.run_one()
    assert client.get("/api/cases", params={"source": "outlook"}).json()["total"] == 1
    assert client.post("/api/sync", json={"mode": "rescan", "lookback_days": 7}).status_code == 200
    assert worker.run_one()
    status = client.get("/api/outlook").json()
    assert status["sync_summary"] == {"scanned": 4, "matched": 1, "new": 0, "existing": 1}
    assert client.get("/api/cases", params={"source": "outlook"}).json()["total"] == 1


def test_rescan_resumes_pagination_and_repeated_clicks_preserve_the_active_scan(composio, backend, monkeypatch):
    from app import worker

    sessions, client = composio
    with sessions() as db:
        connect(db, backend)
        db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "SYNC")).status = "DONE"
        db.commit()
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    original = composio_provider.ComposioOutlookProvider._request
    visited = []
    next_page = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=page2"

    def paginated(provider, transport, url):
        if "/delta?" in url:
            visited.append(url)
            if len(visited) == 1:
                return {"value": [{"id": "ignored", "subject": "Unrelated email"}], "@odata.nextLink": next_page}
        return original(provider, transport, url)

    monkeypatch.setattr(composio_provider.ComposioOutlookProvider, "_request", paginated)
    request = client.post("/api/sync", json={"mode": "rescan", "lookback_days": 14}).json()
    assert worker.run_one()
    assert client.get("/api/outlook").json()["sync_status"] == "PENDING"
    duplicate = client.post("/api/sync", json={"mode": "incremental"}).json()
    assert request["job_id"] == duplicate["job_id"]
    with sessions() as db:
        payload = db.get(ProcessingJob, request["job_id"]).payload
        assert payload["mode"] == "rescan" and payload["lookback_days"] == 14 and payload["started_at"]
    assert worker.run_one() and visited[1] == next_page
    assert client.get("/api/outlook").json()["sync_summary"] == {"scanned": 5, "matched": 1, "new": 1, "existing": 0}


@pytest.fixture
def composio(context, monkeypatch):
    monkeypatch.setattr(settings, "mail_provider", "outlook")
    monkeypatch.setattr(settings, "outlook_transport", "composio")
    monkeypatch.setattr(settings, "outlook_test_mode", True)
    monkeypatch.setattr(settings, "composio_api_key", SecretStr("test-only-composio-project-key"))
    monkeypatch.setattr(settings, "composio_auth_config_id", AUTH_CONFIG)
    monkeypatch.setattr(settings, "composio_poll_interval", 0)
    monkeypatch.setattr(settings, "outlook_client_id", "")
    monkeypatch.setattr(settings, "outlook_client_secret", SecretStr(""))
    return context


@pytest.fixture
def backend(monkeypatch):
    from email import policy
    from email.parser import BytesParser

    parsed = BytesParser(policy=policy.default).parsebytes(mime_message(SUBJECT))
    attachment = next(parsed.iter_attachments()).get_payload(decode=True)
    state = {"requests": [], "scopes": READ_SCOPES.split(","), "fail_delete": False}

    def response(data):
        return httpx.Response(200, json={"status": 200, "headers": {}, "data": data})

    def handler(request):
        state["requests"].append(request)
        assert request.url.host == "backend.composio.dev"
        assert request.headers["x-api-key"] == "test-only-composio-project-key"
        assert "authorization" not in request.headers
        path = request.url.path
        if path.endswith("/connected_accounts/link"):
            payload = json.loads(request.content)
            assert payload["user_id"] == user_id(1) and payload["auth_config_id"] == AUTH_CONFIG
            state["callback"] = payload["callback_url"]
            return httpx.Response(
                201,
                json={"connected_account_id": REMOTE_ID, "redirect_url": "https://connect.composio.dev/link/ln_test"},
            )
        if path.endswith("/connected_accounts/" + REMOTE_ID):
            if request.method == "DELETE":
                assert request.url.params["revoke_on_delete"] == "true"
                return httpx.Response(503 if state["fail_delete"] else 200, json={"success": True})
            return httpx.Response(
                200,
                json={
                    "id": REMOTE_ID,
                    "toolkit": {"slug": "outlook"},
                    "auth_config": {"id": AUTH_CONFIG, "is_composio_managed": True, "is_disabled": False},
                    "status": "ACTIVE",
                    "requested_scopes": state["scopes"],
                    # Current APIs may redact user_id and all credentials.
                },
            )
        assert path == "/api/v3.1/tools/execute/proxy" and request.method == "POST"
        payload = json.loads(request.content)
        assert payload["method"] == "GET" and payload["connected_account_id"] == REMOTE_ID
        assert payload["user_id"] == user_id(1)
        endpoint = urlsplit(payload["endpoint"])
        assert endpoint.hostname == "graph.microsoft.com" and endpoint.scheme == "https"
        if endpoint.path == "/v1.0/me":
            if state.get("profile_status"):
                return httpx.Response(200, json={"status": state["profile_status"], "data": {}, "headers": {}})
            return response({"id": "mailbox-test", "mail": "hr@hospital.example"})
        if endpoint.path.endswith("/delta"):
            if state.get("graph_status"):
                return httpx.Response(
                    200,
                    json={"status": state["graph_status"], "data": {}, "headers": {"Retry-After": "120"}},
                )
            return response(
                {
                    "value": [
                        {"id": "personal", "subject": "Private unrelated email"},
                        {"id": "business", "subject": "[DCC] Department report"},
                        {"id": "incomplete", "subject": "[TALLYV-MVP] Other test"},
                        {"id": "sample", "subject": SUBJECT, "receivedDateTime": "2026-11-02T02:00:00Z"},
                    ],
                    "@odata.deltaLink": CHECKPOINT,
                }
            )
        if endpoint.path.endswith("/messages/sample"):
            return response(
                {
                    "subject": state.get("changed_subject", SUBJECT),
                    "from": {"emailAddress": {"address": "department@hospital.example"}},
                    "toRecipients": [{"emailAddress": {"address": "hr@hospital.example"}}],
                    "internetMessageId": "<composio-mvp-test@example.test>",
                    "body": {"contentType": "text", "content": "Synthetic department summary"},
                    "hasAttachments": True,
                }
            )
        if endpoint.path.endswith("/attachments/workbook-1"):
            return response(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "summary.xlsx",
                    "contentBytes": state.get("attachment_content", base64.b64encode(attachment).decode()),
                }
            )
        assert endpoint.path.endswith("/messages/sample/attachments")
        assert parse_qs(endpoint.query)["$select"] == ["id,name,size"]
        return response(
            {
                "value": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "id": "workbook-1",
                        "name": "summary.xlsx",
                        "size": state.get("attachment_size", len(attachment)),
                    }
                ]
            }
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:

        def factory():
            return ComposioClient(client=http)

        monkeypatch.setattr(composio_auth, "ComposioClient", factory)
        monkeypatch.setattr(composio_provider, "ComposioClient", factory)
        yield state


def connect(db, backend):
    url, cookie = mailbox_auth.begin_connection(db, 1, "http://localhost:8000")
    assert url == "https://connect.composio.dev/link/ln_test"
    state = parse_qs(urlsplit(backend["callback"]).query)["state"][0]
    parameters = {"state": state, "status": "success", "connected_account_id": REMOTE_ID}
    mailbox_auth.complete_connection(db, cookie, parameters)
    return cookie, parameters


def test_composio_reads_workbook_through_proxy_and_runs_existing_pipeline(composio, backend):
    sessions, client = composio
    configure_real_catalog(client)
    with sessions() as db:
        cookie, parameters = connect(db, backend)
        connection = db.get(OutlookConnection, 1)
        assert connection.transport == "composio" and connection.token_cache == ""
        assert mailbox.ready(db) and mailbox.poll_interval() == 0
        assert db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "SYNC")).status == "PENDING"
        with pytest.raises(AppError):
            mailbox_auth.complete_connection(db, cookie, parameters)
        result = mailbox.synchronize_mailbox(db)
        assert result["new"] == 1 and connection.delta_link == CHECKPOINT
        email = db.scalar(select(Email))
        assert email.source_id.startswith("outlook:composio:")
        process_email(db, email.id)
        db.commit()
        assert email.status == "IMPORTED" and email.period_id == "2026-11"
        assert db.scalar(select(AttendanceCase)).cycle_start.isoformat() == "2026-10-31"
        assert mailbox.synchronize_mailbox(db)["existing"] == 1
        db.commit()
    endpoints = [json.loads(r.content)["endpoint"] for r in backend["requests"] if r.url.path.endswith("/proxy")]
    assert not any("personal" in url or "business" in url or "incomplete" in url for url in endpoints)
    assert not any("isRead" in url for url in endpoints)
    listing = client.get("/api/cases", params={"source": "outlook"}).json()
    assert [item["code"] for item in listing["items"]] == ["REAL-001"]
    assert client.get("/api/dashboard").json()["total"] == 1
    exported = load_workbook(BytesIO(client.get("/api/export").content))
    assert "REAL-001" in json.dumps(list(exported.active.values), default=str)
    status = client.get("/api/outlook").json()
    assert status["transport"] == "composio" and status["configured"] and status["test_mode"]
    assert "test-only-composio-project-key" not in json.dumps(status)


@pytest.mark.parametrize("profile_status", [200, 403])
def test_http_connect_and_callback_use_browser_cookie_and_enqueue_initial_sync(composio, backend, profile_status):
    sessions, client = composio
    if profile_status != 200:
        backend["profile_status"] = profile_status
    # Keep the existing HR login cookie while using the API's test origin.
    monkey_origin = "http://testserver"
    settings_uri = settings.outlook_redirect_uri
    try:
        settings.outlook_redirect_uri = monkey_origin + "/api/outlook/callback"
        response = client.post("/api/outlook/connect")
        assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
        state = parse_qs(urlsplit(backend["callback"]).query)["state"][0]
        response = client.get(
            "/api/outlook/callback",
            params={"state": state, "status": "success", "connected_account_id": REMOTE_ID},
            follow_redirects=False,
        )
        assert response.headers["location"] == ("/?outlook=connected" if profile_status == 200 else "/?outlook=failed")
        assert "Max-Age=0" in response.headers["set-cookie"]
        with sessions() as db:
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.kind == "SYNC"))
            assert (job is not None) == (profile_status == 200)
    finally:
        settings.outlook_redirect_uri = settings_uri


@pytest.mark.parametrize("bad", ["cookie", "state", "account", "expired"])
def test_composio_rejects_wrong_browser_state_account_and_expiry(composio, backend, bad):
    sessions, _ = composio
    with sessions() as db:
        _, cookie = mailbox_auth.begin_connection(db, 1, "http://localhost:8000")
        flow = db.scalar(select(OutlookAuthFlow))
        state = parse_qs(urlsplit(backend["callback"]).query)["state"][0]
        assert state not in flow.payload
        if bad == "expired":
            flow.expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        with pytest.raises(AppError):
            mailbox_auth.complete_connection(
                db,
                "wrong-cookie" if bad == "cookie" else cookie,
                {
                    "state": "forged" if bad == "state" else state,
                    "status": "success",
                    "connected_account_id": "ca_someone_else" if bad == "account" else REMOTE_ID,
                },
            )
        assert db.get(OutlookConnection, 1) is None
    assert not any(request.url.path.endswith("/proxy") for request in backend["requests"])


@pytest.mark.parametrize("scopes", [["Mail.Read", "User.Read", "Mail.Send"], ["Mail.Read"], []])
def test_composio_rejects_broad_or_missing_scope_snapshots(composio, backend, scopes):
    sessions, _ = composio
    backend["scopes"] = scopes
    with sessions() as db, pytest.raises(AppError) as caught:
        connect(db, backend)
    assert caught.value.status_code == 403


def test_mvp_cannot_be_disabled_and_transports_cannot_be_silently_switched(composio, backend, monkeypatch):
    sessions, _ = composio
    with sessions() as db:
        connect(db, backend)
        monkeypatch.setattr(settings, "outlook_test_mode", False)
        before = len(backend["requests"])
        assert not mailbox.ready(db)
        with pytest.raises(AppError):
            mailbox.synchronize_mailbox(db)
        assert len(backend["requests"]) == before
        monkeypatch.setattr(settings, "outlook_test_mode", True)
        monkeypatch.setattr(settings, "outlook_transport", "microsoft")
        assert not mailbox.ready(db)
        with pytest.raises(AppError):
            mailbox.synchronize_mailbox(db)
    with pytest.raises(ValidationError, match="synthetic MVP"):
        Settings(
            _env_file=None,
            database_url="sqlite://",
            secret_key="x" * 32,
            demo_password="x" * 12,
            mail_provider="outlook",
            outlook_transport="composio",
            outlook_test_mode=False,
        )


def test_no_attachments_are_fetched_if_message_loses_its_test_tags(composio, backend):
    sessions, _ = composio
    backend["changed_subject"] = "Private email"
    with sessions() as db:
        connect(db, backend)
        assert mailbox.synchronize_mailbox(db)["new"] == 0
        assert db.scalar(select(Email)) is None
    assert not any("/attachments" in request.content.decode() for request in backend["requests"])


def test_oversized_attachment_is_reported_without_downloading_and_advances_checkpoint(composio, backend):
    sessions, client = composio
    configure_real_catalog(client)
    backend["attachment_size"] = 30 * 1024 * 1024
    with sessions() as db:
        connect(db, backend)
        assert mailbox.synchronize_mailbox(db)["new"] == 1
        assert db.get(OutlookConnection, 1).delta_link == CHECKPOINT
        email = db.scalar(select(Email))
        assert "25 MB" in email.body and db.scalar(select(Attachment)) is None
    assert not any("/attachments/workbook-1" in request.content.decode() for request in backend["requests"])


def test_corrupt_attachment_does_not_commit_a_cursor_and_lose_a_message(composio, backend):
    sessions, _ = composio
    backend["attachment_content"] = "not-valid-base64!"
    with sessions() as db:
        connect(db, backend)
        with pytest.raises(ValueError, match="Invalid attachment content"):
            mailbox.synchronize_mailbox(db)
        assert db.get(OutlookConnection, 1).delta_link is None
        assert db.scalar(select(Email)) is None


@pytest.mark.parametrize("code,expected", [(403, 409), (429, 503), (503, 503)])
def test_proxy_preserves_microsoft_permission_and_throttling_errors(composio, backend, code, expected):
    sessions, _ = composio
    with sessions() as db:
        connect(db, backend)
        backend["graph_status"] = code
        with pytest.raises(AppError) as error:
            mailbox.synchronize_mailbox(db)
        assert error.value.status_code == expected
        assert db.get(OutlookConnection, 1).delta_link is None
        if code != 403:
            assert error.value.retry_after == 120


def test_disconnect_revokes_remote_connection_and_local_reads_stop_even_on_failure(composio, backend):
    sessions, client = composio
    with sessions() as db:
        connect(db, backend)
    backend["fail_delete"] = True
    assert client.post("/api/outlook/disconnect").status_code == 503
    with sessions() as db:
        assert not mailbox.ready(db) and db.get(OutlookConnection, 1).status == "DISCONNECTED"
    backend["fail_delete"] = False
    assert client.post("/api/outlook/disconnect").status_code == 200
    assert client.post("/api/sync").status_code == 409
    with sessions() as db:
        assert db.get(OutlookConnection, 1).account_id == ""


def test_proxy_rejects_untrusted_graph_origins_without_sending_a_request(composio):
    def no_network(request):
        raise AssertionError("Untrusted URLs must not reach Composio")

    with httpx.Client(transport=httpx.MockTransport(no_network)) as http, ComposioClient(client=http) as client:
        with pytest.raises(ValueError):
            client.graph_json(REMOTE_ID, 1, "https://outside.invalid/v1.0/me")


def test_worker_configuration_failure_does_not_expire_a_valid_connection(composio, backend, monkeypatch):
    from app import worker

    sessions, client = composio
    with sessions() as db:
        connect(db, backend)
    monkeypatch.setattr(worker, "SessionLocal", sessions)

    def unconfigured_worker(db):
        raise AppError(409, message("composio.configuration_required"))

    monkeypatch.setattr(worker.mailbox, "synchronize_mailbox", unconfigured_worker)
    assert worker.run_one()
    with sessions() as db:
        assert db.get(OutlookConnection, 1).status == "CONNECTED"
    status = client.get("/api/outlook").json()
    assert status["status"] == "CONNECTED"
    assert status["sync_status"] == "PENDING"
    assert status["sync_error"] == message("composio.configuration_required")


def test_worker_authentication_failure_still_requires_reconnection(composio, backend, monkeypatch):
    from app import worker

    sessions, _ = composio
    with sessions() as db:
        connect(db, backend)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    backend["graph_status"] = 403
    assert worker.run_one()
    with sessions() as db:
        assert db.get(OutlookConnection, 1).status == "REAUTH_REQUIRED"


def test_setup_creates_read_only_managed_config_and_preserves_existing_secrets(composio, tmp_path, capsys):
    path = tmp_path / ".env"
    path.write_text("# Existing configuration\nSECRET_KEY=keep-this-secret\nMAIL_PROVIDER=mailpit\n")

    def handler(request):
        assert str(request.url) == API_ROOT + "/auth_configs"
        payload = json.loads(request.content)
        assert payload["auth_config"]["credentials"]["scopes"] == READ_SCOPES
        assert payload["auth_config"]["type"] == "use_composio_managed_auth"
        return httpx.Response(
            201, json={"toolkit": {"slug": "outlook"}, "auth_config": {"id": AUTH_CONFIG, "is_composio_managed": True}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        configure("hidden-test-project-key", path=path, client=client)
    saved = path.read_text()
    assert "SECRET_KEY=keep-this-secret" in saved and saved.count("MAIL_PROVIDER=") == 1
    assert 'OUTLOOK_TRANSPORT="composio"' in saved and 'OUTLOOK_TEST_MODE="true"' in saved
    assert path.stat().st_mode & 0o777 == 0o600
    assert "hidden-test-project-key" not in capsys.readouterr().out


def test_transport_migration_preserves_microsoft_connection_and_blocks_lossy_downgrade():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/e146b20a9c73_add_outlook_transport.py"
    spec = importlib.util.spec_from_file_location("transport_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with create_engine("sqlite://").begin() as connection:
        connection.execute(
            text("CREATE TABLE outlook_connections (id INTEGER PRIMARY KEY, status TEXT, token_cache TEXT)")
        )
        connection.execute(text("INSERT INTO outlook_connections VALUES (1, 'CONNECTED', 'encrypted-original')"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        record = connection.execute(text("SELECT transport, token_cache FROM outlook_connections")).one()
        assert record == ("microsoft", "encrypted-original")
        connection.execute(text("UPDATE outlook_connections SET transport='composio'"))
        with pytest.raises(RuntimeError, match="Disconnect Composio"):
            module.downgrade()
