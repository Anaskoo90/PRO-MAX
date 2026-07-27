import uuid

from app.platform_core.shared_kernel.result import Err, Ok, unwrap
from app.platform_core.shared_kernel.utils import new_uuid7
from app.platform_core.shared_kernel.validation import Specification


def test_result_unwrap_returns_ok_value() -> None:
    assert unwrap(Ok(5)) == 5


def test_result_err_is_distinguishable_from_ok() -> None:
    assert Err("bad").is_err
    assert not Ok(1).is_err


def test_new_uuid7_has_correct_version_and_variant_bits() -> None:
    generated = new_uuid7()
    assert generated.version == 7
    assert generated.variant == uuid.RFC_4122


def test_new_uuid7_is_time_ordered() -> None:
    first = new_uuid7()
    second = new_uuid7()
    assert first.bytes[:6] <= second.bytes[:6]


class _IsEven(Specification[int]):
    def is_satisfied_by(self, candidate: int) -> bool:
        return candidate % 2 == 0


class _IsPositive(Specification[int]):
    def is_satisfied_by(self, candidate: int) -> bool:
        return candidate > 0


def test_specification_and_combinator() -> None:
    spec = _IsEven().and_(_IsPositive())
    assert spec.is_satisfied_by(4) is True
    assert spec.is_satisfied_by(-4) is False
    assert spec.is_satisfied_by(3) is False


def test_specification_not_combinator() -> None:
    spec = _IsEven().not_()
    assert spec.is_satisfied_by(3) is True
    assert spec.is_satisfied_by(4) is False
