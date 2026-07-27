"""
Dead Letter Strategy: after RetryPolicy.max_attempts is exhausted, a message
is routed to its queue's dead_letter_queue_name (QueueSpec) rather than
dropped or retried forever. This module defines the record shape written
alongside it for operator triage (Enterprise Runbooks' DLQ-drain runbook).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.platform_core.shared_kernel.utils import utcnow


class DeadLetterRecord(BaseModel):
    original_queue: str
    routing_key: str
    body: bytes
    headers: dict[str, str]
    failure_reason: str
    attempt_count: int
    dead_lettered_at: datetime = Field(default_factory=utcnow)

    model_config = {"arbitrary_types_allowed": True}
