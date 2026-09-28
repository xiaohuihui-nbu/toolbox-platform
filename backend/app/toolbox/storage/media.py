"""Authenticated media streaming helpers. Object keys stay server-side."""

import re

PREVIEW_MIMES = {
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/ogg": "audio",
    "audio/flac": "audio",
    "audio/x-flac": "audio",
    "audio/webm": "audio",
    "video/mp4": "video",
    "video/webm": "video",
    "video/ogg": "video",
    "video/quicktime": "video",
}


def byte_range(value: str | None, size: int):
    if value is None:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError("invalid byte range")
    start, end = match.groups()
    if not start:
        suffix = int(end)
        if suffix <= 0:
            raise ValueError("invalid suffix")
        return max(0, size - suffix), size - 1
    first = int(start)
    last = min(int(end), size - 1) if end else size - 1
    if first >= size or first > last:
        raise ValueError("unsatisfiable range")
    return first, last
