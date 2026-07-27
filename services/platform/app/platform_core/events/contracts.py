"""
Event Contracts: the envelope every domain and integration event shares.
Integration events additionally carry a schema_version, since — unlike
domain events, which never leave the process — they're a public contract
other bounded contexts and the Plugin SDK's event extension point depend on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class DomainEvent(BaseModel):
    """Raised and handled entirely in-process, within the aggregate's own
    transaction (or immediately after commit). Never serialized to the bus."""

    event_id: UUID = Field(default_factory=new_uuid7)
    occurred_at: datetime = Field(default_factory=utcnow)
    aggregate_id: UUID

    event_type: ClassVar[str] = "domain.event"


class IntegrationEvent(BaseModel):
    """Crosses bounded-context boundaries via the Outbox Pattern + RabbitMQ
    Event Bus (ADR-004, ADR-014). Publishers never know their subscribers
    (ADR-006) — this is the wire contract, versioned independently of the
    Python class that produces it."""

    event_id: UUID = Field(default_factory=new_uuid7)
    occurred_at: datetime = Field(default_factory=utcnow)
    org_id: UUID
    schema_version: int = 1
    payload: dict[str, Any]

    event_type: ClassVar[str] = "integration.event"
