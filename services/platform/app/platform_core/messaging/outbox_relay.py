"""Concurrent-safe PostgreSQL outbox relay for all bounded contexts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform_core.logging.logger import get_logger
from app.platform_core.messaging.bus import MessageBus

_logger = get_logger("messaging.outbox_relay")
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

DEFAULT_OUTBOX_SCHEMAS = (
    "identity",
    "projects",
    "tasks",
    "boards",
    "workflow_engine",
    "discord_integration",
    "ticket_system",
)


@dataclass(frozen=True, slots=True)
class OutboxRelayResult:
    published_count: int
    failed_schema_count: int


class SqlAlchemyOutboxRelay:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        message_bus: MessageBus,
        schemas: tuple[str, ...] = DEFAULT_OUTBOX_SCHEMAS,
        exchange: str = "guilddesk.events",
        batch_size: int = 100,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("Outbox relay batch size must be positive")
        if any(not _SAFE_IDENTIFIER.fullmatch(schema) for schema in schemas):
            raise ValueError("Outbox relay schema names must be safe SQL identifiers")
        self._engine = engine
        self._message_bus = message_bus
        self._schemas = schemas
        self._exchange = exchange
        self._batch_size = batch_size

    async def run_once(self) -> OutboxRelayResult:
        published_count = 0
        failed_schema_count = 0
        for schema in self._schemas:
            try:
                published_count += await self._relay_schema(schema)
            except Exception:
                failed_schema_count += 1
                await _logger.aerror(
                    "outbox_schema_relay_failed",
                    schema=schema,
                    exc_info=True,
                )
        if published_count:
            await _logger.ainfo(
                "outbox_batch_published",
                published_count=published_count,
            )
        return OutboxRelayResult(
            published_count=published_count,
            failed_schema_count=failed_schema_count,
        )

    async def _relay_schema(self, schema: str) -> int:
        # schema comes exclusively from the validated constructor tuple;
        # bind parameters cannot represent SQL identifiers.
        select_sql = text(
            f"""
            SELECT id, event_type, org_id, payload
            FROM {schema}.outbox_messages
            WHERE published_at IS NULL
            ORDER BY created_at, id
            FOR UPDATE SKIP LOCKED
            LIMIT :batch_size
            """
        )
        update_sql = text(
            f"""
            UPDATE {schema}.outbox_messages
            SET published_at = now()
            WHERE id = :message_id AND published_at IS NULL
            """
        )
        published = 0
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    select_sql,
                    {"batch_size": self._batch_size},
                )
            ).mappings().all()
            for row in rows:
                message_id = str(row["id"])
                event_type = str(row["event_type"])
                org_id = str(row["org_id"])
                payload = row["payload"]
                await self._message_bus.publish(
                    exchange=self._exchange,
                    routing_key=event_type,
                    body=json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                    headers={
                        "message_id": message_id,
                        "event_type": event_type,
                        "org_id": org_id,
                        "source_schema": schema,
                        "schema_version": str(payload.get("schema_version", 1)),
                    },
                )
                result = await connection.execute(
                    update_sql,
                    {"message_id": row["id"]},
                )
                if result.rowcount == 1:
                    published += 1
        return published
