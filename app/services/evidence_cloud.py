"""Protect both outbound image endpoints with the same approval check."""

from hashlib import sha256

from app.core.config import settings


class CloudImageNotApproved(ValueError):
    """The exact image was not approved for the cloud test."""


class CloudProviderNotConfigured(ValueError):
    """The selected cloud provider has no endpoint or credentials."""


def require_approved_image(content: bytes) -> None:
    approved = {value.strip().lower() for value in settings.evidence_vision_cloud_test_sha256.split(",")}
    if sha256(content).hexdigest() not in approved:
        raise CloudImageNotApproved()
    if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > 8 * 1024 * 1024:
        raise ValueError("Cloud tests require an approved PNG within the evidence size limit")
