import pytest
from app.platform_core.events.integration_event import (
    append_domain_events_to_outbox,
    domain_event_to_integration_event,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.tasks.domain.events import TaskCreated


class RecordingOutbox:
    def __init__(self) -> None:
        self.events = []

    async def append(self, event) -> None:
        self.events.append(event)


def _task_created_event() -> TaskCreated:
    return TaskCreated(
        aggregate_id=EntityId(new_uuid7()),
        project_id=EntityId(new_uuid7()),
        org_id=OrgId(new_uuid7()),
        title="Mapped task",
    )


def test_domain_event_mapping_preserves_identity_and_serializes_payload() -> None:
    event = _task_created_event()
    org_id = OrgId(new_uuid7())

    integration_event = domain_event_to_integration_event(event, org_id=org_id)

    assert integration_event.event_id == event.event_id
    assert integration_event.occurred_at == event.occurred_at
    assert integration_event.org_id == org_id
    assert integration_event.payload["event_type"] == "tasks.task_created"
    assert integration_event.payload["data"]["aggregate_id"] == str(event.aggregate_id)


@pytest.mark.asyncio
async def test_append_domain_events_writes_each_event_to_outbox() -> None:
    outbox = RecordingOutbox()
    events = [_task_created_event(), _task_created_event()]
    org_id = OrgId(new_uuid7())

    await append_domain_events_to_outbox(outbox, events, org_id=org_id)

    assert [event.event_id for event in outbox.events] == [
        event.event_id for event in events
    ]
    assert {event.org_id for event in outbox.events} == {org_id}
