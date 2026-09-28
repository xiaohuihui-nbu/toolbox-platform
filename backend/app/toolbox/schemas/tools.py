from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextInput(StrictInput):
    text: str = Field(min_length=1, max_length=30000, title="文本内容")


class SpeechInput(StrictInput):
    text: str = Field(min_length=1, max_length=3000, title="朗读内容")
    language: str = Field(default="cmn", pattern="^(cmn|en-us)$", title="语言")
    speed: int = Field(default=160, ge=80, le=260, title="语速")
    pitch: int = Field(default=50, ge=0, le=99, title="音调")
    volume: int = Field(default=100, ge=0, le=200, title="音量")
    format: Literal["wav", "mp3"] = Field(default="wav", title="输出格式")


class MediaInput(StrictInput):
    asset_id: str = Field(pattern=r"^[a-f0-9-]{36}$", title="输入文件")


class NaturalSpeechInput(StrictInput):
    text: str = Field(min_length=1, max_length=1000, title="配音文案")
    voice_id: str = Field(default="female", pattern=r"^[a-zA-Z0-9_-]{1,32}$", title="配音音色")
    speed: float = Field(default=1, ge=0.6, le=1.5, title="语速倍率")
    pause: float = Field(default=0.35, ge=0, le=2, title="段间停顿（秒）")
    format: Literal["wav", "mp3"] = Field(default="mp3", title="输出格式")


class DownloadInput(StrictInput):
    url: HttpUrl = Field(title="视频链接")
    title: str = Field(default="", max_length=160, title="任务标题")
    quality: Literal["best", "1080p", "720p", "480p"] = Field(default="best", title="下载清晰度")
