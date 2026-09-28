"""Opt-in same-source download benchmark; no platform jobs/assets are created."""

import hashlib
import json
import tempfile
import time
from pathlib import Path

from app.toolbox.config import settings
from app.toolbox.runtime.process import command

URL = "https://www.bilibili.com/video/av117322685618746"
results = []
for mode in ("native", "aria2c", "native", "aria2c"):
    with tempfile.TemporaryDirectory(prefix="tb-speed-") as temp:
        directory = Path(temp)
        args = [
            "yt-dlp",
            "--ignore-config",
            "--no-playlist",
            "--no-warnings",
            "--no-progress",
            "--socket-timeout",
            "20",
            "--retries",
            "1",
            "--max-filesize",
            "100M",
            "--proxy",
            settings().download_proxy,
            "-f",
            "bv[protocol=https][ext=mp4]+ba[protocol=https]/b[protocol=https]/b[protocol=http]",
            "--merge-output-format",
            "mp4",
            "-o",
            "download.%(ext)s",
        ]
        if mode == "aria2c":
            args += ["--downloader", "http,https:aria2c", "--downloader-args", "aria2c:-x4 -s4 -j1 -k1M --connect-timeout=10 --timeout=20 --max-tries=2"]
        args += ["--", URL]
        start = time.monotonic()
        command(args, directory, lambda: None, timeout=180)
        output = next(directory.glob("download.*"))
        result = {"mode": mode, "seconds": round(time.monotonic() - start, 2), "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
        results.append(result)
        print(json.dumps(result), flush=True)
print(json.dumps({"results": results}), flush=True)
