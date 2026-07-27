"""Common type aliases shared across every bounded context."""

from __future__ import annotations

from datetime import datetime
from typing import NewType
from uuid import UUID

# Distinct NewTypes (not bare UUID) so a CustomerId can't be passed where a
# TicketId is expected without an explicit cast — cheap correctness at the
# type-checker level, zero runtime cost.
EntityId = NewType("EntityId", UUID)
OrgId = NewType("OrgId", UUID)
UserId = NewType("UserId", UUID)

Timestamp = datetime  # always UTC-aware; see shared_kernel.utils.utcnow()
