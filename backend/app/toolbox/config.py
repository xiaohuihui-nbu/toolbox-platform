from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TB_", extra="ignore")
    database_url: str = "mysql+pymysql://toolbox:toolbox@mysql/toolbox?charset=utf8mb4"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "toolbox"
    s3_secret_key: str = ""
    s3_bucket: str = "toolbox"
    admin_password: str = ""
    cookie_secure: bool = False
    session_hours: int = 24
    max_upload_mb: int = 100
    user_storage_mb: int = 2048
    max_active_jobs: int = 25
    download_proxy: str = "http://egress:8899"
    download_engine: Literal["native", "aria2c"] = "native"
    download_connections: int = Field(default=4, ge=1, le=8)


@lru_cache
def settings() -> Settings:
    return Settings()
