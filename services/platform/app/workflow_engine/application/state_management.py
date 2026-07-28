"""Workflow States submodule: custom states, initial/final/hidden/archived flags."""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.workflow_engine.application.authorization_helpers import WorkflowAuthorization
from app.workflow_engine.application.dtos import WorkflowStateDTO
from app.workflow_engine.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.workflow_engine.domain.entities import WorkflowState, compute_position_between
from app.workflow_engine.domain.events import StateCreated, StateDeleted, StateUpdated
from app.workflow_engine.domain.exceptions import StateInUseError, StateNameAlreadyExistsError, StateNotFoundError, WorkflowNotFoundError


def _to_dto(state: WorkflowState) -> WorkflowStateDTO:
    return WorkflowStateDTO(
        id=state.id, workflow_id=state.workflow_id, name=state.name, position=state.position, is_initial=state.is_initial,
        is_final=state.is_final, is_hidden=state.is_hidden, is_archived=state.is_archived,
        mapped_task_status=state.mapped_task_status,
    )


class WorkflowStateService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        project_context: ProjectContextPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = WorkflowAuthorization(permission_checker=permission_checker, project_context=project_context)

    async def _assert_can_manage_workflow(self, uow, *, workflow_id: EntityId, actor_user_id: UserId):
        workflow = await uow.workflows.get_by_id(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)
        await self._authorization.assert_can_manage(project_id=workflow.project_id, org_id=workflow.org_id, user_id=actor_user_id)
        return workflow

    async def _clear_existing_initial(self, uow, workflow_id: EntityId) -> None:
        states = await uow.states.list_for_workflow(workflow_id)
        for state in states:
            if state.is_initial:
                state.set_initial(False)
                await uow.states.update(state)

    async def create_state(
        self, *, workflow_id: EntityId, actor_user_id: UserId, name: str, is_initial: bool = False,
        is_final: bool = False, is_hidden: bool = False, mapped_task_status: str | None = None,
    ) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            await self._assert_can_manage_workflow(uow, workflow_id=workflow_id, actor_user_id=actor_user_id)
            if await uow.states.get_by_name(workflow_id, name) is not None:
                raise StateNameAlreadyExistsError(name)

            if is_initial:
                await self._clear_existing_initial(uow, workflow_id)

            existing = await uow.states.list_for_workflow(workflow_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            state = WorkflowState.create(
                workflow_id=workflow_id, name=name, position=position, is_initial=is_initial, is_final=is_final,
                is_hidden=is_hidden, mapped_task_status=mapped_task_status,
            )
            await uow.states.add(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateCreated(aggregate_id=state.id, workflow_id=workflow_id, name=name))
            return _to_dto(state)

    async def list_for_workflow(self, *, workflow_id: EntityId) -> list[WorkflowStateDTO]:
        async with self._uow_factory() as uow:
            states = await uow.states.list_for_workflow(workflow_id)
            return [_to_dto(s) for s in states]

    async def _load_state_and_authorize(self, uow, *, state_id: EntityId, actor_user_id: UserId) -> WorkflowState:
        state = await uow.states.get_by_id(state_id)
        if state is None:
            raise StateNotFoundError(state_id)
        await self._assert_can_manage_workflow(uow, workflow_id=state.workflow_id, actor_user_id=actor_user_id)
        return state

    async def rename_state(self, *, state_id: EntityId, actor_user_id: UserId, name: str) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            if await uow.states.get_by_name(state.workflow_id, name) is not None:
                raise StateNameAlreadyExistsError(name)
            state.rename(name)
            await uow.states.update(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateUpdated(aggregate_id=state.id))
            return _to_dto(state)

    async def set_initial(self, *, state_id: EntityId, actor_user_id: UserId) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            await self._clear_existing_initial(uow, state.workflow_id)
            state.set_initial(True)
            await uow.states.update(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateUpdated(aggregate_id=state.id))
            return _to_dto(state)

    async def set_final(self, *, state_id: EntityId, actor_user_id: UserId, is_final: bool) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            state.set_final(is_final)
            await uow.states.update(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateUpdated(aggregate_id=state.id))
            return _to_dto(state)

    async def set_hidden(self, *, state_id: EntityId, actor_user_id: UserId, is_hidden: bool) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            state.set_hidden(is_hidden)
            await uow.states.update(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateUpdated(aggregate_id=state.id))
            return _to_dto(state)

    async def set_archived(self, *, state_id: EntityId, actor_user_id: UserId, is_archived: bool) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            state.set_archived(is_archived)
            await uow.states.update(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateUpdated(aggregate_id=state.id))
            return _to_dto(state)

    async def set_mapped_task_status(self, *, state_id: EntityId, actor_user_id: UserId, status: str | None) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            state.set_mapped_task_status(status)
            await uow.states.update(state)
            await uow.commit()
            await self._dispatcher.dispatch(StateUpdated(aggregate_id=state.id))
            return _to_dto(state)

    async def reorder_state(
        self, *, state_id: EntityId, actor_user_id: UserId, previous_state_id: EntityId | None, next_state_id: EntityId | None,
    ) -> WorkflowStateDTO:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)

            previous_position = None
            if previous_state_id is not None:
                previous = await uow.states.get_by_id(previous_state_id)
                previous_position = previous.position if previous else None
            next_position = None
            if next_state_id is not None:
                nxt = await uow.states.get_by_id(next_state_id)
                next_position = nxt.position if nxt else None

            state.set_position(compute_position_between(previous_position, next_position))
            await uow.states.update(state)
            await uow.commit()
            return _to_dto(state)

    async def delete_state(self, *, state_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            state = await self._load_state_and_authorize(uow, state_id=state_id, actor_user_id=actor_user_id)
            if await uow.transitions.references_state(state_id):
                raise StateInUseError(state_id)
            await uow.states.delete(state_id)
            await uow.commit()
            await self._dispatcher.dispatch(StateDeleted(aggregate_id=state_id))
