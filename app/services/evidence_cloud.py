"""Shared input validation for remote evidence providers."""


class CloudProviderNotConfigured(ValueError):
    """The selected cloud provider has no endpoint or credentials."""


def validate_cloud_image(content: bytes) -> None:
    if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > 8 * 1024 * 1024:
        raise ValueError("Cloud providers require a PNG within the evidence size limit")
