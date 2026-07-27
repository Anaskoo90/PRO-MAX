"""
Cancellation: cooperative cancellation tokens for long-running jobs (report
generation, bulk export) — a job body polls is_cancelled() at safe points
rather than being hard-killed, since a hard kill mid-write could leave
partial state.
"""

from __future__ import annotations

import asyncio
from typing import Protocol


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...

    def cancel(self) -> None: ...


class AsyncCancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    async def wait_cancelled(self) -> None:
        await self._event.wait()


class CancellationRegistry:
    """Maps a running job's id to its token, so an admin-triggered cancel
    (Platform Administrator Guide's job-management surface) can reach it."""

    def __init__(self) -> None:
        self._tokens: dict[str, AsyncCancellationToken] = {}

    def create(self, job_run_id: str) -> AsyncCancellationToken:
        token = AsyncCancellationToken()
        self._tokens[job_run_id] = token
        return token

    def cancel(self, job_run_id: str) -> bool:
        token = self._tokens.get(job_run_id)
        if token is None:
            return False
        token.cancel()
        return True

    def cleanup(self, job_run_id: str) -> None:
        self._tokens.pop(job_run_id, None)
