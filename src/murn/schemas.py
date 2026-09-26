from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    history: list[Message] = Field(default_factory=list)
    source: str = Field(default="unknown", max_length=40)


class ChatResponse(BaseModel):
    message: str
    model: str
    session_id: str


class RPMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100000)


class RPChatRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    messages: list[RPMessage] = Field(min_length=1, max_length=80)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0.05, le=1)
    num_predict: int | None = Field(default=None, ge=32, le=4096)
    source: str = Field(default="rp-creator", max_length=40)


class RPChatResponse(BaseModel):
    message: str
    model: str


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
