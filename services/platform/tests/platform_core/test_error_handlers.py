from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError
from app.platform_core.errors.handlers import register_exception_handlers
from app.platform_core.shared_kernel.error_codes import ErrorCode
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _ForbiddenBusinessRuleError(BusinessRuleViolationError):
    code = ErrorCode.FORBIDDEN

    def __init__(self) -> None:
        super().__init__("test_forbidden", "Access denied")


def test_forbidden_domain_error_maps_to_http_403() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise _ForbiddenBusinessRuleError()

    with TestClient(app) as client:
        response = client.get("/forbidden")

    assert response.status_code == 403
    assert response.json()["code"] == ErrorCode.FORBIDDEN
