"""Pydantic models shared across the API surface."""
from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel, Field


class ConfigPayload(BaseModel):
    api_key: str | None = None  # if omitted, keep existing
    base_url: str = Field(default="https://api.anthropic.com")
    model_name: str = Field(..., min_length=1)
    custom_system_prompt: str = Field(default="")
    provider_hint: Literal["auto", "anthropic", "openai"] = "auto"


class ConfigView(BaseModel):
    configured: bool
    base_url: str
    model_name: str
    custom_system_prompt: str
    provider_hint: str
    api_key_preview: str


class UserProfileView(BaseModel):
    display_name: str
    preferred_style: str
    preferred_domain: str | None
    total_seconds: int


class TopicProgressView(BaseModel):
    topic_id: str
    track_id: str
    unit_id: str
    status: str
    mastery_score: int
    attempts: int
    correct: int
    time_seconds: int
    last_summary: str


class StartSessionPayload(BaseModel):
    topic_id: str
    mode: Literal["learn", "practice", "capstone"] = "learn"
    domain_hint: str | None = None


class ChatMessagePayload(BaseModel):
    session_id: int
    content: str
    action: Literal["answer", "continue", "simpler", "example", "dont_know", "hint"] = "answer"


class ChatTurnResponse(BaseModel):
    session_id: int
    assistant_message: str
    suggestions: list[str] = []
    exercise_active: bool = False
    mastery_delta: int = 0
    outcome: Literal["ongoing", "correct", "incorrect", "complete"] = "ongoing"
    metadata: dict[str, Any] = {}


class EndSessionPayload(BaseModel):
    session_id: int
    outcome: Literal["complete", "abandoned", "checkpoint"] = "complete"


class CapstoneState(BaseModel):
    track_id: str
    phase: str
    checkpoints: list[dict[str, Any]]
    scratchpad: str
