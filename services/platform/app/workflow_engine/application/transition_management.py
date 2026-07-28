"""
Workflow Transitions submodule: create, delete, rename, enable/disable.
Also owns the CRUD surface for everything attached to a transition —
Transition Rules (submodule 4), Workflow Actions (submodule 5), Workflow
Conditions (submodule 6), and checklist-item templates (the
REQUIRED_CHECKLIST_COMPLETION rule's backing data) — since all of these
are configuration owned by a transition, not independent aggregates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import EntityId, UserId
from app.workflow_engine.application.authorization_helpers import WorkflowAuthorization
from app.workflow_engine.application.dtos import (
    TransitionRuleDTO,
    WorkflowActionDTO,
    WorkflowChecklistItemDTO,
    WorkflowConditionDTO,
    WorkflowTransitionDTO,
)
from app.workflow_engine.application.ports import OrgPermissionCheckerPort, ProjectContextPort
from app.workflow_engine.domain.entities import (
    ActionTriggerMode,
    ActionType,
    ConditionOperator,
    ConditionType,
    RuleType,
    TransitionRule,
    WorkflowAction,
    WorkflowChecklistItem,
    WorkflowCondition,
    WorkflowTransition,
    compute_position_between,
)
from app.workflow_engine.domain.events import (
    TransitionCreated,
    TransitionDeleted,
    TransitionDisabled,
    TransitionEnabled,
    TransitionRenamed,
)
from app.workflow_engine.domain.exceptions import (
    ActionNotFoundError,
    ConditionNotFoundError,
    RuleNotFoundError,
    StateNotFoundError,
    TransitionNotFoundError,
    WorkflowNotFoundError,
)


def _transition_to_dto(t: WorkflowTransition) -> WorkflowTransitionDTO:
    return WorkflowTransitionDTO(
        id=t.id, workflow_id=t.workflow_id, name=t.name, from_state_id=t.from_state_id, to_state_id=t.to_state_id,
        position=t.position, enabled=t.enabled, is_automatic=t.is_automatic,
    )


def _rule_to_dto(r: TransitionRule) -> TransitionRuleDTO:
    return TransitionRuleDTO(id=r.id, transition_id=r.transition_id, rule_type=r.rule_type.value, config=r.config)


def _action_to_dto(a: WorkflowAction) -> WorkflowActionDTO:
    return WorkflowActionDTO(
        id=a.id, transition_id=a.transition_id, action_type=a.action_type.value, config=a.config, position=a.position,
        trigger_mode=a.trigger_mode.value, delay_seconds=a.delay_seconds, scheduled_at=a.scheduled_at,
    )


def _condition_to_dto(c: WorkflowCondition) -> WorkflowConditionDTO:
    return WorkflowConditionDTO(id=c.id, transition_id=c.transition_id, condition_type=c.condition_type.value, operator=c.operator.value, value=c.value, position=c.position)


def _checklist_item_to_dto(i: WorkflowChecklistItem) -> WorkflowChecklistItemDTO:
    return WorkflowChecklistItemDTO(id=i.id, transition_id=i.transition_id, label=i.label, position=i.position)


class WorkflowTransitionService:
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

    async def _load_transition_and_authorize(self, uow, *, transition_id: EntityId, actor_user_id: UserId) -> WorkflowTransition:
        transition = await uow.transitions.get_by_id(transition_id)
        if transition is None:
            raise TransitionNotFoundError(transition_id)
        await self._assert_can_manage_workflow(uow, workflow_id=transition.workflow_id, actor_user_id=actor_user_id)
        return transition

    async def create_transition(
        self, *, workflow_id: EntityId, actor_user_id: UserId, name: str, from_state_id: EntityId, to_state_id: EntityId,
        is_automatic: bool = False,
    ) -> WorkflowTransitionDTO:
        async with self._uow_factory() as uow:
            await self._assert_can_manage_workflow(uow, workflow_id=workflow_id, actor_user_id=actor_user_id)
            if await uow.states.get_by_id(from_state_id) is None:
                raise StateNotFoundError(from_state_id)
            if await uow.states.get_by_id(to_state_id) is None:
                raise StateNotFoundError(to_state_id)

            existing = await uow.transitions.list_for_workflow(workflow_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            transition = WorkflowTransition.create(
                workflow_id=workflow_id, name=name, from_state_id=from_state_id, to_state_id=to_state_id,
                position=position, is_automatic=is_automatic,
            )
            await uow.transitions.add(transition)
            await uow.commit()
            await self._dispatcher.dispatch(TransitionCreated(aggregate_id=transition.id, workflow_id=workflow_id, name=name))
            return _transition_to_dto(transition)

    async def list_for_workflow(self, *, workflow_id: EntityId) -> list[WorkflowTransitionDTO]:
        async with self._uow_factory() as uow:
            transitions = await uow.transitions.list_for_workflow(workflow_id)
            return [_transition_to_dto(t) for t in transitions]

    async def rename_transition(self, *, transition_id: EntityId, actor_user_id: UserId, name: str) -> WorkflowTransitionDTO:
        async with self._uow_factory() as uow:
            transition = await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            transition.rename(name)
            await uow.transitions.update(transition)
            await uow.commit()
            await self._dispatcher.dispatch(TransitionRenamed(aggregate_id=transition.id))
            return _transition_to_dto(transition)

    async def enable_transition(self, *, transition_id: EntityId, actor_user_id: UserId) -> WorkflowTransitionDTO:
        async with self._uow_factory() as uow:
            transition = await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            transition.enable()
            await uow.transitions.update(transition)
            await uow.commit()
            await self._dispatcher.dispatch(TransitionEnabled(aggregate_id=transition.id))
            return _transition_to_dto(transition)

    async def disable_transition(self, *, transition_id: EntityId, actor_user_id: UserId) -> WorkflowTransitionDTO:
        async with self._uow_factory() as uow:
            transition = await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            transition.disable()
            await uow.transitions.update(transition)
            await uow.commit()
            await self._dispatcher.dispatch(TransitionDisabled(aggregate_id=transition.id))
            return _transition_to_dto(transition)

    async def set_automatic(self, *, transition_id: EntityId, actor_user_id: UserId, is_automatic: bool) -> WorkflowTransitionDTO:
        async with self._uow_factory() as uow:
            transition = await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            transition.set_automatic(is_automatic)
            await uow.transitions.update(transition)
            await uow.commit()
            return _transition_to_dto(transition)

    async def delete_transition(self, *, transition_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)

            for rule in await uow.rules.list_for_transition(transition_id):
                await uow.rules.delete(rule.id)
            for action in await uow.actions.list_for_transition(transition_id):
                await uow.actions.delete(action.id)
            for condition in await uow.conditions.list_for_transition(transition_id):
                await uow.conditions.delete(condition.id)
            for item in await uow.checklist_items.list_for_transition(transition_id):
                await uow.checklist_items.delete(item.id)

            await uow.transitions.delete(transition_id)
            await uow.commit()
            await self._dispatcher.dispatch(TransitionDeleted(aggregate_id=transition_id))

    # --- Transition Rules (submodule 4) ---

    async def add_rule(self, *, transition_id: EntityId, actor_user_id: UserId, rule_type: RuleType, config: dict[str, Any]) -> TransitionRuleDTO:
        async with self._uow_factory() as uow:
            await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            rule = TransitionRule.create(transition_id=transition_id, rule_type=rule_type, config=config)
            await uow.rules.add(rule)
            await uow.commit()
            return _rule_to_dto(rule)

    async def list_rules(self, *, transition_id: EntityId) -> list[TransitionRuleDTO]:
        async with self._uow_factory() as uow:
            rules = await uow.rules.list_for_transition(transition_id)
            return [_rule_to_dto(r) for r in rules]

    async def remove_rule(self, *, rule_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            rule = await uow.rules.get_by_id(rule_id)
            if rule is None:
                raise RuleNotFoundError(rule_id)
            await self._load_transition_and_authorize(uow, transition_id=rule.transition_id, actor_user_id=actor_user_id)
            await uow.rules.delete(rule_id)
            await uow.commit()

    # --- Workflow Actions (submodule 5) ---

    async def add_action(
        self, *, transition_id: EntityId, actor_user_id: UserId, action_type: ActionType, config: dict[str, Any],
        trigger_mode: ActionTriggerMode = ActionTriggerMode.IMMEDIATE, delay_seconds: float | None = None,
        scheduled_at: datetime | None = None,
    ) -> WorkflowActionDTO:
        async with self._uow_factory() as uow:
            await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            existing = await uow.actions.list_for_transition(transition_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            action = WorkflowAction.create(
                transition_id=transition_id, action_type=action_type, config=config, position=position,
                trigger_mode=trigger_mode, delay_seconds=delay_seconds, scheduled_at=scheduled_at,
            )
            await uow.actions.add(action)
            await uow.commit()
            return _action_to_dto(action)

    async def list_actions(self, *, transition_id: EntityId) -> list[WorkflowActionDTO]:
        async with self._uow_factory() as uow:
            actions = await uow.actions.list_for_transition(transition_id)
            return [_action_to_dto(a) for a in actions]

    async def remove_action(self, *, action_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            action = await uow.actions.get_by_id(action_id)
            if action is None:
                raise ActionNotFoundError(action_id)
            await self._load_transition_and_authorize(uow, transition_id=action.transition_id, actor_user_id=actor_user_id)
            await uow.actions.delete(action_id)
            await uow.commit()

    # --- Workflow Conditions (submodule 6) ---

    async def add_condition(
        self, *, transition_id: EntityId, actor_user_id: UserId, condition_type: ConditionType, operator: ConditionOperator,
        value: Any,
    ) -> WorkflowConditionDTO:
        async with self._uow_factory() as uow:
            await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            existing = await uow.conditions.list_for_transition(transition_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            condition = WorkflowCondition.create(transition_id=transition_id, condition_type=condition_type, operator=operator, value=value, position=position)
            await uow.conditions.add(condition)
            await uow.commit()
            return _condition_to_dto(condition)

    async def list_conditions(self, *, transition_id: EntityId) -> list[WorkflowConditionDTO]:
        async with self._uow_factory() as uow:
            conditions = await uow.conditions.list_for_transition(transition_id)
            return [_condition_to_dto(c) for c in conditions]

    async def remove_condition(self, *, condition_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            condition = await uow.conditions.get_by_id(condition_id)
            if condition is None:
                raise ConditionNotFoundError(condition_id)
            await self._load_transition_and_authorize(uow, transition_id=condition.transition_id, actor_user_id=actor_user_id)
            await uow.conditions.delete(condition_id)
            await uow.commit()

    # --- Checklist item templates (backing REQUIRED_CHECKLIST_COMPLETION) ---

    async def add_checklist_item(self, *, transition_id: EntityId, actor_user_id: UserId, label: str) -> WorkflowChecklistItemDTO:
        async with self._uow_factory() as uow:
            await self._load_transition_and_authorize(uow, transition_id=transition_id, actor_user_id=actor_user_id)
            existing = await uow.checklist_items.list_for_transition(transition_id)
            position = compute_position_between(existing[-1].position if existing else None, None)
            item = WorkflowChecklistItem.create(transition_id=transition_id, label=label, position=position)
            await uow.checklist_items.add(item)
            await uow.commit()
            return _checklist_item_to_dto(item)

    async def list_checklist_items(self, *, transition_id: EntityId) -> list[WorkflowChecklistItemDTO]:
        async with self._uow_factory() as uow:
            items = await uow.checklist_items.list_for_transition(transition_id)
            return [_checklist_item_to_dto(i) for i in items]

    async def remove_checklist_item(self, *, item_id: EntityId, actor_user_id: UserId) -> None:
        async with self._uow_factory() as uow:
            item = await uow.checklist_items.get_by_id(item_id)
            if item is None:
                return
            await self._load_transition_and_authorize(uow, transition_id=item.transition_id, actor_user_id=actor_user_id)
            await uow.checklist_items.delete(item_id)
            await uow.commit()
