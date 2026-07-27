import pytest

from app.platform_core.plugins.version_compat import (
    PluginVersionIncompatibleError,
    SemVer,
    check_compatible,
)


def test_semver_ordering() -> None:
    assert SemVer.parse("1.0.0") < SemVer.parse("1.2.3")
    assert SemVer.parse("2.0.0") > SemVer.parse("1.9.9")


def test_check_compatible_passes_within_range() -> None:
    check_compatible(
        plugin_id="demo",
        host_sdk_version=SemVer.parse("1.5.0"),
        min_sdk_version=SemVer.parse("1.0.0"),
        max_sdk_version=SemVer.parse("2.0.0"),
    )


def test_check_compatible_rejects_below_minimum() -> None:
    with pytest.raises(PluginVersionIncompatibleError):
        check_compatible(
            plugin_id="demo",
            host_sdk_version=SemVer.parse("0.9.0"),
            min_sdk_version=SemVer.parse("1.0.0"),
            max_sdk_version=None,
        )


def test_check_compatible_rejects_above_maximum() -> None:
    with pytest.raises(PluginVersionIncompatibleError):
        check_compatible(
            plugin_id="demo",
            host_sdk_version=SemVer.parse("3.0.0"),
            min_sdk_version=SemVer.parse("1.0.0"),
            max_sdk_version=SemVer.parse("2.0.0"),
        )
