from __future__ import annotations

from app.ai_gateway.application.service import AiCompletionService


def get_ai_completion_service() -> AiCompletionService:
    raise NotImplementedError("AiCompletionService dependency not wired")
