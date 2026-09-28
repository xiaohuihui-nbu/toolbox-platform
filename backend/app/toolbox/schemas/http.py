from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Preferences(BaseModel):
    mode: str = Field(pattern="^(light|dark|system)$")
    accent: str = Field(pattern="^(coral|blue|green|violet)$")
    favorites: list[str] = Field(default_factory=list, max_length=100)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ToolToggle(BaseModel):
    enabled: bool


class CreateUser(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]{2,31}$")
    name: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=12, max_length=128)


class JobInput(BaseModel):
    tool_id: str
    params: dict


class JobPatch(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=200)
    params: dict | None = None


class JobBatchDelete(BaseModel):
    model_config = {"extra": "forbid"}
    job_ids: list[UUID] = Field(min_length=1, max_length=100)


class VideoSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=120)
    platform: Literal["bilibili", "youtube"] = "bilibili"
    limit: int = Field(default=8, ge=1, le=12)


class BatchVideoItem(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=160)


class BatchVideoInput(BaseModel):
    items: list[BatchVideoItem] = Field(min_length=1, max_length=20)
    quality: Literal["best", "1080p", "720p", "480p"] = "best"
