"""Workflow Transitions HTTP routes: create/rename/delete/enable/disable,
plus Transition Rules, Workflow Actions, Workflow Conditions, and
checklist-item templates attached to a transition."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.workflow_engine.application.transition_management import WorkflowTransitionService
from app.workflow_engine.domain.entities import ActionTriggerMode, ActionType, ConditionOperator, ConditionType, RuleType
from app.workflow_engine.presentation import deps
from app.workflow_engine.presentation.schemas import (
    AddActionRequest,
    AddChecklistItemRequest,
    AddConditionRequest,
    AddRuleRequest,
    CreateTransitionRequest,
    RenameTransitionRequest,
    SetAutomaticRequest,
    TransitionRuleResponse,
    WorkflowActionResponse,
    WorkflowChecklistItemResponse,
    WorkflowConditionResponse,
    WorkflowTransitionResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["workflow-transitions"])


def _to_response(dto) -> WorkflowTransitionResponse:
    return WorkflowTransitionResponse(
        id=dto.id, workflow_id=dto.workflow_id, name=dto.name, from_state_id=dto.from_state_id, to_state_id=dto.to_state_id,
        position=dto.position, enabled=dto.enabled, is_automatic=dto.is_automatic,
    )


@router.post("/workflows/{workflow_id}/transitions", response_model=DataResponse[WorkflowTransitionResponse], status_code=201)
async def create_transition(
    workflow_id: str,
    request: CreateTransitionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowTransitionResponse]:
    transition = await service.create_transition(
        workflow_id=UUID(workflow_id), actor_user_id=claims.subject_user_id, name=request.name,
        from_state_id=request.from_state_id, to_state_id=request.to_state_id, is_automatic=request.is_automatic,
    )
    return DataResponse(data=_to_response(transition))


@router.get("/workflows/{workflow_id}/transitions", response_model=DataResponse[list[WorkflowTransitionResponse]])
async def list_transitions(
    workflow_id: str,
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[list[WorkflowTransitionResponse]]:
    transitions = await service.list_for_workflow(workflow_id=UUID(workflow_id))
    return DataResponse(data=[_to_response(t) for t in transitions])


@router.patch("/transitions/{transition_id}", response_model=DataResponse[WorkflowTransitionResponse])
async def rename_transition(
    transition_id: str,
    request: RenameTransitionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowTransitionResponse]:
    transition = await service.rename_transition(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id, name=request.name)
    return DataResponse(data=_to_response(transition))


@router.post("/transitions/{transition_id}/enable", response_model=DataResponse[WorkflowTransitionResponse])
async def enable_transition(
    transition_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowTransitionResponse]:
    transition = await service.enable_transition(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(transition))


@router.post("/transitions/{transition_id}/disable", response_model=DataResponse[WorkflowTransitionResponse])
async def disable_transition(
    transition_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowTransitionResponse]:
    transition = await service.disable_transition(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(transition))


@router.put("/transitions/{transition_id}/automatic", response_model=DataResponse[WorkflowTransitionResponse])
async def set_transition_automatic(
    transition_id: str,
    request: SetAutomaticRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowTransitionResponse]:
    transition = await service.set_automatic(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id, is_automatic=request.is_automatic)
    return DataResponse(data=_to_response(transition))


@router.delete("/transitions/{transition_id}", status_code=204)
async def delete_transition(
    transition_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> None:
    await service.delete_transition(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id)


# --- Transition Rules ---

@router.post("/transitions/{transition_id}/rules", response_model=DataResponse[TransitionRuleResponse], status_code=201)
async def add_rule(
    transition_id: str,
    request: AddRuleRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[TransitionRuleResponse]:
    rule = await service.add_rule(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id, rule_type=RuleType(request.rule_type), config=request.config)
    return DataResponse(data=TransitionRuleResponse(id=rule.id, transition_id=rule.transition_id, rule_type=rule.rule_type, config=rule.config))


@router.get("/transitions/{transition_id}/rules", response_model=DataResponse[list[TransitionRuleResponse]])
async def list_rules(
    transition_id: str,
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[list[TransitionRuleResponse]]:
    rules = await service.list_rules(transition_id=UUID(transition_id))
    return DataResponse(data=[TransitionRuleResponse(id=r.id, transition_id=r.transition_id, rule_type=r.rule_type, config=r.config) for r in rules])


@router.delete("/rules/{rule_id}", status_code=204)
async def remove_rule(
    rule_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> None:
    await service.remove_rule(rule_id=UUID(rule_id), actor_user_id=claims.subject_user_id)


# --- Workflow Actions ---

@router.post("/transitions/{transition_id}/actions", response_model=DataResponse[WorkflowActionResponse], status_code=201)
async def add_action(
    transition_id: str,
    request: AddActionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowActionResponse]:
    action = await service.add_action(
        transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id, action_type=ActionType(request.action_type),
        config=request.config, trigger_mode=ActionTriggerMode(request.trigger_mode), delay_seconds=request.delay_seconds,
        scheduled_at=request.scheduled_at,
    )
    return DataResponse(data=WorkflowActionResponse(
        id=action.id, transition_id=action.transition_id, action_type=action.action_type, config=action.config,
        position=action.position, trigger_mode=action.trigger_mode, delay_seconds=action.delay_seconds, scheduled_at=action.scheduled_at,
    ))


@router.get("/transitions/{transition_id}/actions", response_model=DataResponse[list[WorkflowActionResponse]])
async def list_actions(
    transition_id: str,
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[list[WorkflowActionResponse]]:
    actions = await service.list_actions(transition_id=UUID(transition_id))
    return DataResponse(data=[
        WorkflowActionResponse(id=a.id, transition_id=a.transition_id, action_type=a.action_type, config=a.config, position=a.position, trigger_mode=a.trigger_mode, delay_seconds=a.delay_seconds, scheduled_at=a.scheduled_at)
        for a in actions
    ])


@router.delete("/actions/{action_id}", status_code=204)
async def remove_action(
    action_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> None:
    await service.remove_action(action_id=UUID(action_id), actor_user_id=claims.subject_user_id)


# --- Workflow Conditions ---

@router.post("/transitions/{transition_id}/conditions", response_model=DataResponse[WorkflowConditionResponse], status_code=201)
async def add_condition(
    transition_id: str,
    request: AddConditionRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowConditionResponse]:
    condition = await service.add_condition(
        transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id, condition_type=ConditionType(request.condition_type),
        operator=ConditionOperator(request.operator), value=request.value,
    )
    return DataResponse(data=WorkflowConditionResponse(id=condition.id, transition_id=condition.transition_id, condition_type=condition.condition_type, operator=condition.operator, value=condition.value, position=condition.position))


@router.get("/transitions/{transition_id}/conditions", response_model=DataResponse[list[WorkflowConditionResponse]])
async def list_conditions(
    transition_id: str,
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[list[WorkflowConditionResponse]]:
    conditions = await service.list_conditions(transition_id=UUID(transition_id))
    return DataResponse(data=[
        WorkflowConditionResponse(id=c.id, transition_id=c.transition_id, condition_type=c.condition_type, operator=c.operator, value=c.value, position=c.position)
        for c in conditions
    ])


@router.delete("/conditions/{condition_id}", status_code=204)
async def remove_condition(
    condition_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> None:
    await service.remove_condition(condition_id=UUID(condition_id), actor_user_id=claims.subject_user_id)


# --- Checklist item templates ---

@router.post("/transitions/{transition_id}/checklist-items", response_model=DataResponse[WorkflowChecklistItemResponse], status_code=201)
async def add_checklist_item(
    transition_id: str,
    request: AddChecklistItemRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[WorkflowChecklistItemResponse]:
    item = await service.add_checklist_item(transition_id=UUID(transition_id), actor_user_id=claims.subject_user_id, label=request.label)
    return DataResponse(data=WorkflowChecklistItemResponse(id=item.id, transition_id=item.transition_id, label=item.label, position=item.position))


@router.get("/transitions/{transition_id}/checklist-items", response_model=DataResponse[list[WorkflowChecklistItemResponse]])
async def list_checklist_items(
    transition_id: str,
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> DataResponse[list[WorkflowChecklistItemResponse]]:
    items = await service.list_checklist_items(transition_id=UUID(transition_id))
    return DataResponse(data=[WorkflowChecklistItemResponse(id=i.id, transition_id=i.transition_id, label=i.label, position=i.position) for i in items])


@router.delete("/checklist-items/{item_id}", status_code=204)
async def remove_checklist_item(
    item_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: WorkflowTransitionService = Depends(deps.get_workflow_transition_service),
) -> None:
    await service.remove_checklist_item(item_id=UUID(item_id), actor_user_id=claims.subject_user_id)
