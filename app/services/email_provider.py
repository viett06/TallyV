from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.i18n import message


@dataclass
class IncomingEmail:
    source_id: str
    message_id: str | None
    sender: str
    recipient: str
    subject: str
    body: str
    received_at: datetime
    attachments: list[tuple[str, bytes]]


class EmailProvider(Protocol):
    def messages(self) -> list[IncomingEmail]: ...


class MailpitProvider:
    """Local test mailbox only. Read/unread state is never an ingestion cursor."""

    def messages(self):
        result = []
        with httpx.Client(base_url=settings.mailpit_url, timeout=20, trust_env=False, follow_redirects=False) as client:
            offset = 0
            while True:
                response = client.get("/api/v1/messages", params={"start": offset, "limit": 100})
                response.raise_for_status()
                page = response.json()
                messages = page.get("messages", [])
                for item in messages:
                    source_id = item["ID"]
                    raw_response = client.get(f"/api/v1/message/{source_id}/raw")
                    raw_response.raise_for_status()
                    if len(raw_response.content) > 25 * 1024 * 1024:
                        result.append(
                            IncomingEmail(
                                source_id,
                                None,
                                item.get("From", {}).get("Address", ""),
                                "hr@demo.invalid",
                                str(item.get("Subject", "")),
                                message("emails.oversized_body"),
                                datetime.now(timezone.utc),
                                [],
                            )
                        )
                        continue
                    parsed_message = BytesParser(policy=policy.default).parsebytes(raw_response.content)
                    body = parsed_message.get_body(preferencelist=("plain",))
                    body_text = body.get_content() if body else message("emails.html_not_rendered")
                    attachments = []
                    for part in parsed_message.iter_attachments():
                        content = part.get_payload(decode=True) or b""
                        attachments.append((str(part.get_filename() or "unnamed")[:300], content))
                    senders = getaddresses([str(parsed_message.get("From", ""))])
                    sender = senders[0][1].lower() if senders else ""
                    recipients = ", ".join(
                        address.lower() for _, address in getaddresses(parsed_message.get_all("To", []))
                    )
                    try:
                        received = datetime.fromisoformat(item["Created"].replace("Z", "+00:00"))
                    except (KeyError, ValueError):
                        try:
                            received = parsedate_to_datetime(parsed_message.get("Date"))
                        except (ValueError, TypeError, IndexError):
                            received = datetime.now(timezone.utc)
                    if received.tzinfo is None:
                        received = received.replace(tzinfo=timezone.utc)
                    result.append(
                        IncomingEmail(
                            source_id,
                            str(parsed_message["Message-ID"]) if parsed_message["Message-ID"] else None,
                            sender,
                            recipients,
                            str(parsed_message.get("Subject", "")),
                            str(body_text)[:50000],
                            received,
                            attachments,
                        )
                    )
                offset += len(messages)
                if not messages or offset >= page.get("total", 0):
                    break
        return sorted(result, key=lambda item: item.received_at)
