"""
Prompt Interface: template rendering + variable validation, matching the
`PromptVariableValidationSpecification` referenced in the Domain Modeling &
DDD Blueprint and the prompt_versions.variables JSONB structure from the
Physical Database Schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.platform_core.shared_kernel.validation import Specification

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    template_body: str
    variable_names: frozenset[str]

    @classmethod
    def parse(cls, template_body: str) -> "PromptTemplate":
        names = frozenset(_VARIABLE_PATTERN.findall(template_body))
        return cls(template_body=template_body, variable_names=names)

    def render(self, variables: dict[str, Any]) -> str:
        missing = self.variable_names - variables.keys()
        if missing:
            raise ValueError(f"Missing prompt variables: {sorted(missing)}")

        def _substitute(match: re.Match[str]) -> str:
            return str(variables[match.group(1)])

        return _VARIABLE_PATTERN.sub(_substitute, self.template_body)


class PromptVariableValidationSpecification(Specification[dict[str, Any]]):
    def __init__(self, required_variables: frozenset[str]) -> None:
        self._required = required_variables

    def is_satisfied_by(self, candidate: dict[str, Any]) -> bool:
        return self._required.issubset(candidate.keys())
