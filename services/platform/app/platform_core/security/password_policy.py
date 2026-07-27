"""Password Policies: composable strength rules, evaluated at registration
and password-change time."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    min_length: int = 12
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_symbol: bool = True
    max_length: int = 128

    def violations(self, password: str) -> list[str]:
        issues: list[str] = []
        if len(password) < self.min_length:
            issues.append(f"Password must be at least {self.min_length} characters")
        if len(password) > self.max_length:
            issues.append(f"Password must be at most {self.max_length} characters")
        if self.require_uppercase and not re.search(r"[A-Z]", password):
            issues.append("Password must contain an uppercase letter")
        if self.require_lowercase and not re.search(r"[a-z]", password):
            issues.append("Password must contain a lowercase letter")
        if self.require_digit and not re.search(r"\d", password):
            issues.append("Password must contain a digit")
        if self.require_symbol and not re.search(r"[^\w\s]", password):
            issues.append("Password must contain a symbol")
        return issues

    def is_valid(self, password: str) -> bool:
        return not self.violations(password)


DEFAULT_PASSWORD_POLICY = PasswordPolicy()
