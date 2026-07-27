"""
Metrics: the Golden Signals (latency, traffic, errors, saturation) exposed
via OpenTelemetry's metrics API — Adopt-tier per the platform's Technical
Radar. Vendor-agnostic: an OTel Collector (infrastructure/observability)
handles export, so this module never imports a specific backend SDK.
"""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

from opentelemetry import metrics

_meter = metrics.get_meter("guilddesk.platform")

request_counter = _meter.create_counter(
    "guilddesk.http.requests", unit="1", description="HTTP requests processed"
)
request_duration_histogram = _meter.create_histogram(
    "guilddesk.http.request.duration", unit="ms", description="HTTP request duration"
)
job_duration_histogram = _meter.create_histogram(
    "guilddesk.job.duration", unit="ms", description="Background job duration"
)
error_counter = _meter.create_counter(
    "guilddesk.errors", unit="1", description="Handled and unhandled errors"
)


@contextmanager
def measure_duration_ms(histogram: metrics.Histogram, **attributes: str) -> Iterator[None]:
    start = perf_counter()
    try:
        yield
    finally:
        histogram.record((perf_counter() - start) * 1000, attributes=attributes)
