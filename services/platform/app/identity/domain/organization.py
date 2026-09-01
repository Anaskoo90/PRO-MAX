"""
Organization aggregate.

This is the first time an `organizations` table/entity has been specified
anywhere in the GuildDesk documentation or code — `org_id` has been used as
a column and RLS predicate across every prior document since the Platform
Administrator Guide first flagged its absence as a standing gap. This
resolves it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.identity.domain.events import (
    OrganizationCreated,
    OrganizationOwnershipTransferred,
    OrganizationSettingsUpdated,
    OrganizationStatusChanged,
)
from app.identity.domain.exceptions import InvalidOrganizationSlugError
from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.platform_core.shared_kernel.validation import Specification

import re

_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{1,48}[a-z0-9])?$")


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


def _validate_slug(slug: str) -> str:
    if not _SLUG_PATTERN.match(slug):
        raise InvalidOrganizationSlugError(slug)
    return slug


class Organization(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        slug: str,
        owner_user_id: UserId,
        status: OrganizationStatus,
        settings: dict[str, Any] | None = None,
        description: str | None = None,
        logo_url: str | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.name = name
        self.slug = _validate_slug(slug)
        self.owner_user_id = owner_user_id
        self.status = status
        self.settings = settings or {}
        self.description = description
        self.logo_url = logo_url
        self.version = version

    @classmethod
    def create(cls, *, name: str, slug: str, owner_user_id: UserId) -> "Organization":
        org = cls(
            id=EntityId(new_uuid7()),
            name=name,
            slug=slug,
            owner_user_id=owner_user_id,
            status=OrganizationStatus.ACTIVE,
        )
        org.record_event(OrganizationCreated(aggregate_id=org.id, name=name, slug=slug, owner_user_id=owner_user_id))
        return org

    def rename(self, new_name: str) -> None:
        self.name = new_name

    def change_slug(self, new_slug: str) -> None:
        """Same validation as creation-time — a slug is still a slug once
        the org already exists. Uniqueness against other organizations is
        an application-layer concern (needs a repository lookup), not
        something this entity can check on its own."""
        self.slug = _validate_slug(new_slug)

    def update_description(self, description: str) -> None:
        self.description = description

    def update_logo_url(self, logo_url: str | None) -> None:
        self.logo_url = logo_url

    def update_settings(self, patch: dict[str, Any]) -> None:
        self.settings = {**self.settings, **patch}
        self.record_event(OrganizationSettingsUpdated(aggregate_id=self.id, changed_keys=list(patch.keys())))

    def transfer_ownership(self, new_owner_user_id: UserId) -> None:
        previous_owner = self.owner_user_id
        self.owner_user_id = new_owner_user_id
        self.record_event(
            OrganizationOwnershipTransferred(
                aggregate_id=self.id, previous_owner_user_id=previous_owner, new_owner_user_id=new_owner_user_id
            )
        )

    def suspend(self) -> None:
        self.status = OrganizationStatus.SUSPENDED
        self.record_event(OrganizationStatusChanged(aggregate_id=self.id, status=self.status.value))

    def reactivate(self) -> None:
        self.status = OrganizationStatus.ACTIVE
        self.record_event(OrganizationStatusChanged(aggregate_id=self.id, status=self.status.value))

    def deactivate(self) -> None:
        self.status = OrganizationStatus.DEACTIVATED
        self.record_event(OrganizationStatusChanged(aggregate_id=self.id, status=self.status.value))

    def is_active(self) -> bool:
        return self.status == OrganizationStatus.ACTIVE

    def ip_allowlist(self) -> list[str]:
        return list(self.settings.get("ip_allowlist", []))

    def ip_denylist(self) -> list[str]:
        return list(self.settings.get("ip_denylist", []))


class OrganizationActiveSpecification(Specification[Organization]):
    def is_satisfied_by(self, candidate: Organization) -> bool:
        return candidate.is_active()
