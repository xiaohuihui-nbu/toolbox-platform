"""Opt-in download-only comparison. Run on each project's actual network, with no DB writes."""

import argparse
import hashlib
import json
import signal
import tempfile
import time
from pathlib import Path

started = time.monotonic()
from yt_dlp import YoutubeDL  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--profile", choices=["legacy", "toolbox"], required=True)
parser.add_argument("--proxy", default="")
parser.add_argument("--url", default="https://www.bilibili.com/video/av117322685618746")
args = parser.parse_args()
signal.alarm(180)
events = {}


def progress(status):
    elapsed = round(time.monotonic() - started, 3)
    if status["status"] == "downloading":
        events.setdefault("first_progress_s", elapsed)
    elif status["status"] == "finished":
        events["download_finished_s"] = elapsed


class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


with tempfile.TemporaryDirectory(prefix="download-compare-") as temp:
    options = {
        "quiet": True, "no_warnings": True, "logger": QuietLogger(),
        "noplaylist": True, "ignoreconfig": True, "proxy": args.proxy,
        "outtmpl": str(Path(temp) / "download.%(ext)s"), "merge_output_format": "mp4",
        "socket_timeout": 20, "retries": 1, "max_filesize": 100 * 1024 * 1024,
        "progress_hooks": [progress],
        "format": (
            "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b"
            if args.profile == "legacy" else
            "bv[height<=?1080][protocol=https][ext=mp4]+ba[protocol=https]/b[height<=?1080][protocol=https]/b[height<=?1080][protocol=http]"
        ),
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(args.url, download=True)
        elapsed = round(time.monotonic() - started, 3)
        files = [path for path in Path(temp).glob("download.*") if path.suffix not in {".part", ".ytdl"}]
        output = files[0]
        result = {
            "profile": args.profile, "proxy": bool(args.proxy), "seconds": elapsed,
            **events, "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "format_id": info.get("format_id"), "height": info.get("height"),
        }
    except Exception as exc:
        result = {"profile": args.profile, "proxy": bool(args.proxy), "seconds": round(time.monotonic() - started, 3), "error_type": type(exc).__name__}
    print(json.dumps(result), flush=True)
