from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.identity.application.security import AuditLogQueryService
from app.identity.domain.audit import AuditEventCategory, AuditLogRecord
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.projects.domain.audit import (
    ProjectsAuditEventCategory,
    ProjectsAuditLogRecord,
)

pytestmark = pytest.mark.asyncio


class _AuditLogs:
    def __init__(self, records: list) -> None:
        self.records = records
        self.calls: list[dict] = []

    async def list_for_org(self, org_id, *, category=None, limit: int = 50):
        self.calls.append({"org_id": org_id, "category": category, "limit": limit})
        records = [record for record in self.records if record.org_id == org_id]
        if category is not None:
            records = [record for record in records if record.category == category]
        records.sort(key=lambda record: record.occurred_at, reverse=True)
        return records[:limit]


class _UnitOfWork:
    def __init__(self, audit_logs: _AuditLogs) -> None:
        self.audit_logs = audit_logs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _identity_record(org_id: OrgId, occurred_at: datetime) -> AuditLogRecord:
    return AuditLogRecord(
        id=new_uuid7(),
        org_id=org_id,
        category=AuditEventCategory.AUTHENTICATION,
        action="login",
        actor_user_id=UserId(new_uuid7()),
        resource_type="user",
        resource_id=str(new_uuid7()),
        ip_address="203.0.113.10",
        occurred_at=occurred_at,
    )


def _project_record(
    org_id: OrgId, occurred_at: datetime
) -> ProjectsAuditLogRecord:
    return ProjectsAuditLogRecord(
        id=new_uuid7(),
        org_id=org_id,
        category=ProjectsAuditEventCategory.PROJECT_CHANGE,
        action="project_created",
        actor_user_id=UserId(new_uuid7()),
        resource_type="project",
        resource_id=str(new_uuid7()),
        occurred_at=occurred_at,
    )


async def test_audit_query_merges_context_sources_in_reverse_chronological_order() -> None:
    org_id = OrgId(new_uuid7())
    now = datetime.now(UTC)
    identity_logs = _AuditLogs([_identity_record(org_id, now - timedelta(minutes=1))])
    project_logs = _AuditLogs([_project_record(org_id, now)])
    service = AuditLogQueryService(
        uow_factory=lambda: _UnitOfWork(identity_logs)
    )
    service.register_source(
        source="projects",
        uow_factory=lambda: _UnitOfWork(project_logs),
        category_type=ProjectsAuditEventCategory,
    )

    records = await service.list_for_org(org_id=org_id)

    assert [record.source for record in records] == ["projects", "identity"]
    assert [record.action for record in records] == ["project_created", "login"]
    assert records[1].ip_address == "203.0.113.10"
    assert records[0].ip_address is None


async def test_audit_query_filters_category_across_compatible_sources() -> None:
    org_id = OrgId(new_uuid7())
    now = datetime.now(UTC)
    identity_logs = _AuditLogs([_identity_record(org_id, now)])
    project_logs = _AuditLogs([_project_record(org_id, now)])
    service = AuditLogQueryService(
        uow_factory=lambda: _UnitOfWork(identity_logs)
    )
    service.register_source(
        source="projects",
        uow_factory=lambda: _UnitOfWork(project_logs),
        category_type=ProjectsAuditEventCategory,
    )

    records = await service.list_for_org(
        org_id=org_id, category="project_change"
    )

    assert [record.source for record in records] == ["projects"]
    assert identity_logs.calls == []
    assert project_logs.calls[0]["category"] is ProjectsAuditEventCategory.PROJECT_CHANGE


async def test_audit_query_filters_source_and_applies_a_global_limit() -> None:
    org_id = OrgId(new_uuid7())
    now = datetime.now(UTC)
    identity_logs = _AuditLogs(
        [
            _identity_record(org_id, now),
            _identity_record(org_id, now - timedelta(seconds=1)),
        ]
    )
    project_logs = _AuditLogs([_project_record(org_id, now + timedelta(seconds=1))])
    service = AuditLogQueryService(
        uow_factory=lambda: _UnitOfWork(identity_logs)
    )
    service.register_source(
        source="projects",
        uow_factory=lambda: _UnitOfWork(project_logs),
        category_type=ProjectsAuditEventCategory,
    )

    records = await service.list_for_org(
        org_id=org_id, source="identity", limit=1
    )

    assert len(records) == 1
    assert records[0].source == "identity"
    assert project_logs.calls == []
