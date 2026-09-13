from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AiMessageRequest(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class AiCompletionRequest(BaseModel):
    messages: list[AiMessageRequest] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0, le=2)


class AiCompletionResponse(BaseModel):
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
