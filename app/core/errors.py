"""Application errors, translated to the existing HTTP contract at the API edge."""

from typing import Any


class AppError(Exception):
    def __init__(self, status_code: int, detail: str | dict[str, Any]):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail if isinstance(detail, str) else detail.get("message", "Application error"))


class MailboxReauthenticationRequired(AppError):
    """The mailbox credential itself requires user reauthorization."""

    def __init__(self, detail: str):
        super().__init__(409, detail)
