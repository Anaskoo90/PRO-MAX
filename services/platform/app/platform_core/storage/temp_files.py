"""Temporary Files: scoped temp-file handling for streaming
upload-processing pipelines (e.g. virus-scan-then-persist), guaranteeing
cleanup even on error."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def temporary_file(suffix: str = "") -> Iterator[Path]:
    fd, raw_path = tempfile.mkstemp(suffix=suffix)
    path = Path(raw_path)
    try:
        yield path
    finally:
        import os

        os.close(fd)
        path.unlink(missing_ok=True)
