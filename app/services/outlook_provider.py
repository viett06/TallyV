"""Read one Graph delta page per job; commit the cursor with the imported emails."""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import settings
from app.core.i18n import message
from app.core.time import utcnow
from app.services.email_provider import IncomingEmail

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
MAX_MESSAGE_BYTES = 25 * 1024 * 1024


def graph_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "graph.microsoft.com"
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not parsed.path.startswith("/v1.0/")
    ):
        raise ValueError("Graph pagination must remain on the Microsoft Graph origin")
    return value


class GraphError(Exception):
    def __init__(self, status: int, retry_after: str = ""):
        self.status = status
        self.retry_after = min(3600, max(1, int(retry_after))) if retry_after.isdigit() else 30
        super().__init__(f"Microsoft Graph returned HTTP {status}")


class OutlookProvider:
    def __init__(self, connection, token: str, *, client=None):
        self.connection = connection
        self.mailbox_address = connection.mailbox
        self.checkpoint = connection.delta_link
        self.has_more = False
        self.sync_days = settings.outlook_sync_days
        self.scanned = 0
        self.matched = 0
        self.allowed_senders: set[str] = set()
        self.test_mode = settings.outlook_test_mode
        self.source_prefix = "outlook:"
        self.client = client
        self.headers = {"Authorization": "Bearer " + token, "Prefer": 'IdType="ImmutableId", odata.maxpagesize=10'}

    def initial_url(self):
        since = (utcnow() - timedelta(days=self.sync_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        parameters = httpx.QueryParams(
            {
                "changeType": "created",
                "$select": "id,subject,from,internetMessageId,receivedDateTime",
                "$filter": "receivedDateTime ge " + since,
                "$top": "10",
            }
        )
        return GRAPH_ROOT + "/me/mailFolders/inbox/messages/delta?" + str(parameters)

    def _request(self, client, url):
        response = client.get(graph_url(url), headers=self.headers)
        if response.status_code != 200:
            raise GraphError(response.status_code, response.headers.get("Retry-After", ""))
        return response.json()

    def _mime(self, client, message_id):
        url = GRAPH_ROOT + "/me/messages/" + quote(message_id, safe="") + "/$value"
        with client.stream("GET", url, headers=self.headers) as response:
            if response.status_code in {404, 410}:
                return None
            if response.status_code != 200:
                raise GraphError(response.status_code, response.headers.get("Retry-After", ""))
            parts, size = [], 0
            for part in response.iter_bytes():
                size += len(part)
                if size > MAX_MESSAGE_BYTES:
                    return False
                parts.append(part)
        return b"".join(parts)

    def _messages(self, client):
        url = self.connection.delta_link or self.initial_url()
        try:
            page = self._request(client, url)
        except GraphError as error:
            if error.status != 410:
                raise
            page = self._request(client, self.initial_url())
        checkpoint = page.get("@odata.nextLink") or page.get("@odata.deltaLink")
        if not checkpoint:
            raise ValueError("Graph did not return a durable synchronization checkpoint")
        graph_url(checkpoint)
        for entry in page.get("value", []):
            self.scanned += 1
            sender = entry.get("from", {}).get("emailAddress", {}).get("address", "").lower()
            subject = entry.get("subject", "")
            business_tag = bool(re.search(r"\[DCC\]", subject, re.IGNORECASE))
            test_tag = bool(re.search(r"\[TALLYV-MVP\]", subject, re.IGNORECASE))
            eligible = (
                (business_tag and test_tag)
                if self.test_mode
                else (business_tag or sender in self.allowed_senders)
            )
            if "@removed" in entry or not eligible:
                continue
            self.matched += 1
            content = self._mime(client, entry["id"])
            if content is None:
                continue
            identity = f"{self.connection.account_id}:{self.connection.mailbox_id}:{entry['id']}"
            source_id = self.source_prefix + hashlib.sha256(identity.encode()).hexdigest()
            received = datetime.fromisoformat(entry["receivedDateTime"].replace("Z", "+00:00"))
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            if content is False:
                yield IncomingEmail(
                    source_id,
                    entry.get("internetMessageId"),
                    entry.get("from", {}).get("emailAddress", {}).get("address", "").lower(),
                    self.mailbox_address,
                    entry.get("subject", ""),
                    message("outlook.message_too_large"),
                    received,
                    [],
                )
                continue
            mail = BytesParser(policy=policy.default).parsebytes(content)
            body = mail.get_body(preferencelist=("plain",))
            senders = getaddresses([str(mail.get("From", ""))])
            addresses = [
                self.mailbox_address,
                *[address.lower() for _, address in getaddresses(mail.get_all("To", []))],
            ]
            attachments = [
                (str(part.get_filename() or "unnamed")[:300], part.get_payload(decode=True) or b"")
                for part in mail.iter_attachments()
            ]
            yield IncomingEmail(
                source_id,
                str(mail["Message-ID"]) if mail["Message-ID"] else None,
                senders[0][1].lower() if senders else "",
                ", ".join(dict.fromkeys(addresses))[:200],
                str(mail.get("Subject", entry.get("subject", ""))),
                str(body.get_content())[:50000] if body else message("emails.html_not_rendered"),
                received,
                attachments,
            )
        self.checkpoint = checkpoint
        self.has_more = bool(page.get("@odata.nextLink"))

    def messages(self):
        if self.client is not None:
            yield from self._messages(self.client)
        else:
            with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
                yield from self._messages(client)
