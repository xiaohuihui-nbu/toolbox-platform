from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolContext:
    params: dict
    owner_id: int
    directory: Path
    check: Callable[[], None]
    job_id: str | None = None
    attempt: str | None = None


@dataclass(frozen=True)
class ToolResult:
    output: Path


@dataclass(frozen=True)
class ToolSpec:
    descriptor: dict
    version: str = "1.0.0"

    def validate(self):
        data = self.descriptor
        if data["mode"] not in {"job", "browser", "request"}:
            raise ValueError("Unsupported execution mode")
        if data["mode"] == "job" and (not data.get("schema") or not data.get("handler")):
            raise ValueError("Job plugin requires input schema and approved handler")
        return {**data, "version": self.version}
