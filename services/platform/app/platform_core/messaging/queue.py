"""Queue Abstractions: naming + declaration conventions layered over MessageBus."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueueSpec:
    """One queue per (consuming bounded context, event family), per the
    Integration Architecture's queue-topology convention."""

    name: str
    routing_keys: tuple[str, ...]
    dead_letter_exchange: str
    max_retries: int = 5

    @property
    def dead_letter_queue_name(self) -> str:
        return f"{self.name}.dlq"


def queue_spec_for(context_name: str, event_family: str, routing_keys: list[str]) -> QueueSpec:
    base = f"guilddesk.{context_name}.{event_family}"
    return QueueSpec(
        name=base,
        routing_keys=tuple(routing_keys),
        dead_letter_exchange=f"{base}.dlx",
    )
