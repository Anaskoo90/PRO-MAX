"""Identity value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass

#  Deliberately narrower than full RFC 5322 (which technically permits
#  quoted local-parts containing almost any character, including `<`/`>`):
#  a bare `[^@\s]+` local-part check let HTML/script-injection-shaped
#  strings like `<script>...</script>@example.com` through, since they
#  contain no `@` or whitespace themselves. Restricting the local-part and
#  domain to a known-safe character set closes that off, and rejects
#  legitimate but exotic addresses in favor of a two-layer defense
#  (this check, plus normal output-encoding wherever email is rendered).
_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$"
)


class InvalidEmailError(ValueError):
    def __init__(self, raw: str) -> None:
        super().__init__(f"'{raw}' is not a valid email address")


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if not _EMAIL_PATTERN.match(self.value):
            raise InvalidEmailError(self.value)
        # Normalize: lowercase, so "User@Example.com" and "user@example.com"
        # collide on the (org_id, email) partial unique index as intended.
        object.__setattr__(self, "value", self.value.strip().lower())

    def __str__(self) -> str:
        return self.value
