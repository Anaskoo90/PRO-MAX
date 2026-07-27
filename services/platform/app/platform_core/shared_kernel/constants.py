"""Platform-wide constants (cross-cutting policy defaults, ADR-derived)."""

from __future__ import annotations

# Timeouts (seconds) — Architecture Review Extension §9
TIMEOUT_SYNC_SECONDS = 10
TIMEOUT_EXTERNAL_SECONDS = 30
TIMEOUT_AI_SECONDS = 60

# Circuit breaker
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_FAILURE_RATE = 0.5
CIRCUIT_BREAKER_WINDOW_SIZE = 30

# Graceful shutdown
GRACEFUL_SHUTDOWN_SECONDS = 30

# Pagination
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

# Header names
HEADER_CORRELATION_ID = "X-Correlation-Id"
HEADER_API_VERSION = "X-API-Version"
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"
