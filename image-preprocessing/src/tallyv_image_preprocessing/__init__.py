"""Standalone offline preprocessing. No application, database, queue or AI imports."""

import asyncio

from .processor import Outcome, ProfileSet, SanitizedImage, process


async def process_async(content: bytes, profiles: ProfileSet) -> Outcome:
    """Run CPU/image work off the caller's event loop."""
    return await asyncio.to_thread(process, content, profiles)


__all__ = ["Outcome", "ProfileSet", "SanitizedImage", "process", "process_async"]
