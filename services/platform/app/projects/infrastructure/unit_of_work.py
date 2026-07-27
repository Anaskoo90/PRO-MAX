"""Unit of Work for the `projects` schema — one AsyncSession per request/
command, one commit, identical shape to Identity's IdentityUnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.projects.infrastructure.outbox import SqlAlchemyOutboxWriter
from app.projects.infrastructure.repositories import (
    SqlAlchemyProjectMembershipRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyProjectsAuditLogRepository,
    SqlAlchemyProjectTemplateRepository,
    SqlAlchemyWorkspaceMembershipRepository,
    SqlAlchemyWorkspaceRepository,
)


class ProjectsUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.workspaces: SqlAlchemyWorkspaceRepository | None = None
        self.workspace_memberships: SqlAlchemyWorkspaceMembershipRepository | None = None
        self.projects: SqlAlchemyProjectRepository | None = None
        self.project_memberships: SqlAlchemyProjectMembershipRepository | None = None
        self.project_templates: SqlAlchemyProjectTemplateRepository | None = None
        self.audit_logs: SqlAlchemyProjectsAuditLogRepository | None = None
        self.outbox: SqlAlchemyOutboxWriter | None = None

    async def __aenter__(self) -> "ProjectsUnitOfWork":
        self.session = self._session_factory()
        self.workspaces = SqlAlchemyWorkspaceRepository(self.session)
        self.workspace_memberships = SqlAlchemyWorkspaceMembershipRepository(self.session)
        self.projects = SqlAlchemyProjectRepository(self.session)
        self.project_memberships = SqlAlchemyProjectMembershipRepository(self.session)
        self.project_templates = SqlAlchemyProjectTemplateRepository(self.session)
        self.audit_logs = SqlAlchemyProjectsAuditLogRepository(self.session)
        self.outbox = SqlAlchemyOutboxWriter(self.session, event_type="projects.integration_event")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()
