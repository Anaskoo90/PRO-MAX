"""Standard Responses: the success-envelope counterpart to
platform_core.errors.responses.ErrorResponse."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from app.platform_core.shared_kernel.dtos import PagedResult

T = TypeVar("T")


class DataResponse(BaseModel, Generic[T]):
    data: T


class PagedResponse(BaseModel, Generic[T]):
    data: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def from_paged_result(cls, result: PagedResult[T]) -> "PagedResponse[T]":
        return cls(
            data=result.items,
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            total_pages=result.total_pages,
        )
