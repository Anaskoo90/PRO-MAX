import pytest
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.workflow_engine.application.authorization_helpers import WorkflowAuthorization
from app.workflow_engine.application.ports import ProjectSummary
from app.workflow_engine.domain.exceptions import ProjectNotAccessibleError

from tests.workflow_engine.unit.fakes import AllowAllPermissionChecker, FakeProjectContext


@pytest.fixture
def authorization_context():
    org_id = OrgId(new_uuid7())
    project_id = EntityId(new_uuid7())
    authorization = WorkflowAuthorization(
        permission_checker=AllowAllPermissionChecker(),
        project_context=FakeProjectContext(
            project=ProjectSummary(
                id=project_id,
                org_id=org_id,
                workspace_id=new_uuid7(),
                status="active",
            )
        ),
    )
    return authorization, project_id, org_id, UserId(new_uuid7())


@pytest.mark.asyncio
async def test_cross_tenant_rbac_cannot_authorize_workflows(
    authorization_context,
) -> None:
    authorization, project_id, _org_id, user_id = authorization_context
    caller_org_id = OrgId(new_uuid7())

    for check in (
        authorization.can_view,
        authorization.can_manage,
        authorization.can_execute,
        authorization.can_manage_automation,
    ):
        with pytest.raises(ProjectNotAccessibleError):
            await check(
                project_id=project_id, org_id=caller_org_id, user_id=user_id
            )


@pytest.mark.asyncio
async def test_same_tenant_rbac_can_authorize_workflows(
    authorization_context,
) -> None:
    authorization, project_id, org_id, user_id = authorization_context

    assert await authorization.can_view(
        project_id=project_id, org_id=org_id, user_id=user_id
    )
    assert await authorization.can_manage(
        project_id=project_id, org_id=org_id, user_id=user_id
    )
    assert await authorization.can_execute(
        project_id=project_id, org_id=org_id, user_id=user_id
    )
    assert await authorization.can_manage_automation(
        project_id=project_id, org_id=org_id, user_id=user_id
    )
