from __future__ import annotations

from app.main import app
from app.platform_core.shared_kernel.utils import new_uuid7
from fastapi.testclient import TestClient

client = TestClient(app)


def test_notification_inbox_routes_require_authentication() -> None:
    notification_id = new_uuid7()

    assert client.get("/api/v1/users/me/notifications").status_code == 401
    assert client.get("/api/v1/users/me/notifications/unread-count").status_code == 401
    assert client.post("/api/v1/users/me/notifications/read-all").status_code == 401
    assert (
        client.post(
            f"/api/v1/users/me/notifications/{notification_id}/read"
        ).status_code
        == 401
    )
