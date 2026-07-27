"""Retry Policies: exponential backoff with jitter for message redelivery
and outbound calls, per the Architecture Review Extension's cross-cutting
resilience policies."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter_ratio: float = 0.2

    def delay_for_attempt(self, attempt: int) -> float:
        """attempt is 1-indexed (first retry = attempt 1)."""
        exponential = min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)
        jitter = exponential * self.jitter_ratio * random.uniform(-1, 1)
        return max(0.0, exponential + jitter)

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts


DEFAULT_RETRY_POLICY = RetryPolicy()
