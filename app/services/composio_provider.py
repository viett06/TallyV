"""Read tagged Outlook messages through Composio without exporting Microsoft tokens."""

import base64
import binascii
import re
from email.message import EmailMessage
from urllib.parse import quote

from app.core.i18n import message
from app.services.composio_client import ComposioClient, require_mvp
from app.services.outlook_provider import GRAPH_ROOT, MAX_MESSAGE_BYTES, GraphError, OutlookProvider


class ComposioOutlookProvider(OutlookProvider):
    def __init__(self, connection, *, client=None):
        super().__init__(connection, "", client=client)
        self.test_mode = True
        self.source_prefix = "outlook:composio:"

    def _request(self, client, url):
        return client.graph_json(self.connection.account_id, self.connection.owner_id, url)

    def _mime(self, client, message_id):
        root = GRAPH_ROOT + "/me/messages/" + quote(message_id, safe="")
        try:
            item = self._request(
                client,
                root + "?$select=id,subject,from,toRecipients,internetMessageId,body,hasAttachments",
            )
        except GraphError as error:
            if error.status in {404, 410}:
                return None
            raise
        subject = item.get("subject", "")
        if not re.search(r"\[TALLYV-MVP\]", subject, re.I) or not re.search(r"\[DCC\]", subject, re.I):
            return None
        mail = EmailMessage()
        mail["Subject"] = subject
        mail["From"] = item.get("from", {}).get("emailAddress", {}).get("address", "")
        recipients = [entry.get("emailAddress", {}).get("address", "") for entry in item.get("toRecipients", [])]
        mail["To"] = ", ".join(recipients) or self.mailbox_address
        if item.get("internetMessageId"):
            mail["Message-ID"] = item["internetMessageId"]
        body = item.get("body") or {}
        text = (
            body.get("content", "")
            if body.get("contentType", "").lower() == "text"
            else message("emails.html_not_rendered")
        )
        mail.set_content(text[:50000])
        size = len(text.encode())
        if size > MAX_MESSAGE_BYTES:
            return False
        url = root + "/attachments?$select=id,name,size" if item.get("hasAttachments") else None
        visited = set()
        while url:
            if url in visited or len(visited) >= 100:
                raise ValueError("Invalid attachment pagination")
            visited.add(url)
            page = self._request(client, url)
            for attachment in page.get("value", []):
                kind = attachment.get("@odata.type")
                if kind and kind != "#microsoft.graph.fileAttachment":
                    continue
                declared_size = attachment.get("size")
                if not isinstance(declared_size, int) or declared_size < 0 or not attachment.get("id"):
                    raise ValueError("Invalid attachment metadata returned by the mailbox")
                if size + declared_size > MAX_MESSAGE_BYTES:
                    return False
                detail = self._request(client, root + "/attachments/" + quote(attachment["id"], safe=""))
                if detail.get("@odata.type") not in {None, "#microsoft.graph.fileAttachment"}:
                    continue
                encoded = detail.get("contentBytes")
                if not isinstance(encoded, str):
                    raise ValueError("Missing attachment content returned by the mailbox")
                if len(encoded) > ((MAX_MESSAGE_BYTES - size + 2) // 3) * 4:
                    return False
                try:
                    content = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    raise ValueError("Invalid attachment content returned by the mailbox") from None
                size += len(content)
                if size > MAX_MESSAGE_BYTES:
                    return False
                mail.add_attachment(
                    content,
                    maintype="application",
                    subtype="octet-stream",
                    filename=str(detail.get("name") or attachment.get("name") or "unnamed")[:300],
                )
            url = page.get("@odata.nextLink")
        return mail.as_bytes()

    def messages(self):
        require_mvp()
        if self.client is not None:
            yield from self._messages(self.client)
        else:
            with ComposioClient() as client:
                yield from self._messages(client)
