from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class ChatScopePayload(BaseModel):
    mode: str = Field(default="all", max_length=16)
    corpus_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    allow_common_knowledge: bool = False


class CreateSessionRequest(BaseModel):
    title: str = Field(default="", max_length=120)
    scope: ChatScopePayload | None = None


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    scope: ChatScopePayload | None = None


class SendMessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    scope: ChatScopePayload | None = None
