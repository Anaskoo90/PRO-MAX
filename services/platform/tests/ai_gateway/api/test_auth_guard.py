from __future__ import annotations

import pytest
from app.ai_gateway.application.service import AiCompletionDTO
from app.ai_gateway.presentation import deps
from app.main import app, identity_module
from app.platform_core.shared_kernel.utils import new_uuid7
from fastapi.testclient import TestClient
from tests.api_session_stub import allow_active_test_sessions, issue_session_bound_test_token

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _active_test_sessions():
    with allow_active_test_sessions(app):
        yield


class _CompletionServiceSpy:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def complete(self, **kwargs) -> AiCompletionDTO:
        self.calls.append(kwargs)
        return AiCompletionDTO(
            content="answer",
            provider="test",
            model="test-model",
            input_tokens=2,
            output_tokens=1,
            finish_reason="stop",
        )


def _headers(org_id):
    token = issue_session_bound_test_token(
        identity_module.token_service,
        user_id=new_uuid7(),
        org_id=org_id,
    )
    return {"Authorization": f"Bearer {token}"}


def test_ai_completion_requires_authentication() -> None:
    org_id = new_uuid7()
    response = client.post(
        f"/api/v1/organizations/{org_id}/ai/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 401


def test_cross_tenant_ai_request_is_denied_before_service_access() -> None:
    org_a = new_uuid7()
    org_b = new_uuid7()
    service = _CompletionServiceSpy()
    app.dependency_overrides[deps.get_ai_completion_service] = lambda: service
    try:
        response = client.post(
            f"/api/v1/organizations/{org_b}/ai/completions",
            headers=_headers(org_a),
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    finally:
        app.dependency_overrides.pop(deps.get_ai_completion_service, None)

    assert response.status_code == 403
    assert service.calls == []


def test_same_tenant_ai_request_reaches_wired_service() -> None:
    org_id = new_uuid7()
    service = _CompletionServiceSpy()
    app.dependency_overrides[deps.get_ai_completion_service] = lambda: service
    try:
        response = client.post(
            f"/api/v1/organizations/{org_id}/ai/completions",
            headers=_headers(org_id),
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 25,
                "temperature": 0.1,
            },
        )
    finally:
        app.dependency_overrides.pop(deps.get_ai_completion_service, None)

    assert response.status_code == 200
    assert response.json()["data"]["content"] == "answer"
    assert service.calls[0]["org_id"] == org_id
    assert service.calls[0]["max_tokens"] == 25


def test_ai_completion_route_is_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/organizations/{org_id}/ai/completions" in paths
