from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    history: list[Message] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    model: str
    session_id: str


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    width: int | None = Field(default=None, ge=64, le=4096)
    height: int | None = Field(default=None, ge=64, le=4096)
    seed: int | None = None


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
