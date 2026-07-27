"""Pagination: shared query-param model + offset/limit computation, used by
every list endpoint across every bounded context."""

from __future__ import annotations

from fastapi import Query
from pydantic import BaseModel

from app.platform_core.shared_kernel.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class PageParams(BaseModel):
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)
