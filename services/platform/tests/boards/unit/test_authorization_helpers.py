import pytest

from app.boards.application.authorization_helpers import BoardAuthorization
from app.boards.application.ports import ProjectSummary
from app.boards.domain.exceptions import ProjectNotAccessibleError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.boards.unit.fakes import AllowAllPermissionChecker, FakeProjectContext


@pytest.fixture
def authorization_context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    authorization = BoardAuthorization(
        permission_checker=AllowAllPermissionChecker(),
        project_context=FakeProjectContext(
            project=ProjectSummary(id=project_id, org_id=org_id, workspace_id=new_uuid7(), status="active")
        ),
    )
    return authorization, project_id, org_id, UserId(new_uuid7())


@pytest.mark.asyncio
async def test_cross_tenant_rbac_cannot_view_or_manage_boards(authorization_context) -> None:
    authorization, project_id, _org_id, user_id = authorization_context
    caller_org_id = OrgId(new_uuid7())

    with pytest.raises(ProjectNotAccessibleError):
        await authorization.can_view(project_id=project_id, org_id=caller_org_id, user_id=user_id)
    with pytest.raises(ProjectNotAccessibleError):
        await authorization.can_manage(project_id=project_id, org_id=caller_org_id, user_id=user_id)


@pytest.mark.asyncio
async def test_same_tenant_rbac_can_view_and_manage_boards(authorization_context) -> None:
    authorization, project_id, org_id, user_id = authorization_context

    assert await authorization.can_view(project_id=project_id, org_id=org_id, user_id=user_id) is True
    assert await authorization.can_manage(project_id=project_id, org_id=org_id, user_id=user_id) is True
