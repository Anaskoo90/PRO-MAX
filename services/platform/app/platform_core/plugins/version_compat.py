"""Version Compatibility: semver range check between a plugin's declared
min/max SDK version and the host's actual SDK version, enforced before
on_load() is ever called."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> "SemVer":
        parts = raw.split(".")
        if len(parts) != 3:
            raise ValueError(f"'{raw}' is not a valid semver string")
        major, minor, patch = (int(p) for p in parts)
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class PluginVersionIncompatibleError(Exception):
    def __init__(self, plugin_id: str, host_version: SemVer, min_version: SemVer, max_version: SemVer | None) -> None:
        bound = f"{min_version}..{max_version or '*'}"
        super().__init__(
            f"Plugin '{plugin_id}' requires SDK version {bound}, host is {host_version}"
        )


def check_compatible(
    *, plugin_id: str, host_sdk_version: SemVer, min_sdk_version: SemVer, max_sdk_version: SemVer | None
) -> None:
    if host_sdk_version < min_sdk_version:
        raise PluginVersionIncompatibleError(plugin_id, host_sdk_version, min_sdk_version, max_sdk_version)
    if max_sdk_version is not None and host_sdk_version > max_sdk_version:
        raise PluginVersionIncompatibleError(plugin_id, host_sdk_version, min_sdk_version, max_sdk_version)
