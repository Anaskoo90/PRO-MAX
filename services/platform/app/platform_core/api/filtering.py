"""
Filtering: a small, safe filter-expression model (field/operator/value)
that maps to a SQLAlchemy WHERE clause, so route handlers never build raw
SQL from query params. Each repository declares which fields are
filterable; anything else is rejected rather than silently ignored.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class FilterOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"


class FilterExpression(BaseModel):
    field: str
    operator: FilterOperator
    value: Any


class UnfilterableFieldError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(f"Field '{field}' is not filterable on this resource")


def validate_filters(
    filters: list[FilterExpression], allowed_fields: set[str]
) -> list[FilterExpression]:
    for f in filters:
        if f.field not in allowed_fields:
            raise UnfilterableFieldError(f.field)
    return filters
