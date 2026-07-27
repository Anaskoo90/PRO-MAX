"""
Common utilities, notably the platform's UUIDv7 generator.

PostgreSQL has no native UUIDv7 generator (see the Physical Database Schema
document's flagged note) — v7 ids are generated here, at the application
layer, and passed into inserts explicitly rather than relying on a column
DEFAULT.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid7() -> uuid.UUID:
    """
    Generate a UUIDv7 (RFC 9562): 48-bit millisecond timestamp prefix +
    74 bits of randomness. Monotonic-ish and index-friendly, unlike v4 —
    this is why it was chosen platform-wide for primary keys.
    """
    unix_ms = int(time.time() * 1000)
    ts_bytes = unix_ms.to_bytes(6, byteorder="big")
    rand_bytes = os.urandom(10)

    b = bytearray(ts_bytes + rand_bytes)
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(b))
