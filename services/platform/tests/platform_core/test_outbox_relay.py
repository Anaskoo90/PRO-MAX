from __future__ import annotations

import json

import pytest
from app.platform_core.messaging.outbox_relay import SqlAlchemyOutboxRelay
from app.platform_core.shared_kernel.utils import new_uuid7


class _FakeResult:
    def __init__(self, *, rows=None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[dict], *, fail_select: bool = False) -> None:
        self.rows = rows
        self.fail_select = fail_select
        self.updated_ids: list[object] = []

    async def execute(self, statement, parameters):
        sql = str(statement)
        if "SELECT id" in sql:
            if self.fail_select:
                raise RuntimeError("database unavailable")
            return _FakeResult(rows=self.rows)
        self.updated_ids.append(parameters["message_id"])
        return _FakeResult(rowcount=1)


class _BeginContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeEngine:
    def __init__(self, connections: list[_FakeConnection]) -> None:
        self.connections = connections

    def begin(self):
        return _BeginContext(self.connections.pop(0))


class _RecordingBus:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    async def publish(self, **kwargs) -> None:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("broker unavailable")


def _row(*, event_type: str = "tasks.integration_event") -> dict:
    message_id = new_uuid7()
    org_id = new_uuid7()
    return {
        "id": message_id,
        "event_type": event_type,
        "org_id": org_id,
        "payload": {
            "event_id": str(message_id),
            "org_id": str(org_id),
            "schema_version": 2,
            "payload": {"kind": "task_created"},
        },
    }


@pytest.mark.asyncio
async def test_outbox_relay_publishes_then_marks_each_row() -> None:
    rows = [_row(), _row()]
    connection = _FakeConnection(rows)
    bus = _RecordingBus()
    relay = SqlAlchemyOutboxRelay(
        engine=_FakeEngine([connection]),
        message_bus=bus,
        schemas=("tasks",),
        batch_size=10,
    )

    result = await relay.run_once()

    assert result.published_count == 2
    assert result.failed_schema_count == 0
    assert connection.updated_ids == [rows[0]["id"], rows[1]["id"]]
    assert bus.calls[0]["exchange"] == "guilddesk.events"
    assert bus.calls[0]["routing_key"] == "tasks.integration_event"
    assert bus.calls[0]["headers"]["source_schema"] == "tasks"
    assert bus.calls[0]["headers"]["schema_version"] == "2"
    assert json.loads(bus.calls[0]["body"]) == rows[0]["payload"]


@pytest.mark.asyncio
async def test_publish_failure_leaves_row_unmarked_for_retry() -> None:
    connection = _FakeConnection([_row()])
    relay = SqlAlchemyOutboxRelay(
        engine=_FakeEngine([connection]),
        message_bus=_RecordingBus(fail=True),
        schemas=("identity",),
    )

    result = await relay.run_once()

    assert result.published_count == 0
    assert result.failed_schema_count == 1
    assert connection.updated_ids == []


@pytest.mark.asyncio
async def test_one_broken_schema_does_not_block_other_contexts() -> None:
    good_row = _row(event_type="projects.integration_event")
    failed = _FakeConnection([], fail_select=True)
    succeeded = _FakeConnection([good_row])
    bus = _RecordingBus()
    relay = SqlAlchemyOutboxRelay(
        engine=_FakeEngine([failed, succeeded]),
        message_bus=bus,
        schemas=("identity", "projects"),
    )

    result = await relay.run_once()

    assert result.published_count == 1
    assert result.failed_schema_count == 1
    assert succeeded.updated_ids == [good_row["id"]]


def test_outbox_relay_rejects_untrusted_schema_identifiers() -> None:
    with pytest.raises(ValueError, match="safe SQL identifiers"):
        SqlAlchemyOutboxRelay(
            engine=_FakeEngine([]),
            message_bus=_RecordingBus(),
            schemas=("tasks; DROP TABLE tasks.tasks",),
        )
