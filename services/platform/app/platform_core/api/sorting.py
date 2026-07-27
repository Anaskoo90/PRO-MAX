"""Sorting: shared sort-expression parsing (?sort=-created_at,name)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SortField:
    field: str
    descending: bool


class UnsortableFieldError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(f"Field '{field}' is not sortable on this resource")


def parse_sort(sort_param: str | None, allowed_fields: set[str]) -> list[SortField]:
    if not sort_param:
        return []
    fields: list[SortField] = []
    for raw in sort_param.split(","):
        raw = raw.strip()
        if not raw:
            continue
        descending = raw.startswith("-")
        field = raw[1:] if descending else raw
        if field not in allowed_fields:
            raise UnsortableFieldError(field)
        fields.append(SortField(field=field, descending=descending))
    return fields
