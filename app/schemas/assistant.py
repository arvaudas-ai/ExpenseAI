from typing import Any

from pydantic import BaseModel, Field, field_validator


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be empty.")
        return cleaned


class AssistantChatResponse(BaseModel):
    answer: str
    source: str
    currency: str
    metrics: dict[str, Any] = Field(default_factory=dict)
