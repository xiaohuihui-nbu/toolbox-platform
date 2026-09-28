from urllib.parse import urlsplit

from app.toolbox.config import settings
from app.toolbox.contracts.tools import ToolContext, ToolResult
from app.toolbox.runtime.process import command
from plugins.video_download.errors import classify_error


def format_selector(quality):
    cap = {"1080p": 1080, "720p": 720, "480p": 480}.get(quality)
    # Direct media URLs can lack height metadata; keep these usable.
    height = f"[height<=?{cap}]" if cap else ""
    return f"bv{height}[protocol=https][ext=mp4]+ba[protocol=https]/b{height}[protocol=https]/b{height}[protocol=http]"


def execute(context: ToolContext) -> ToolResult:
    params, directory, check = context.params, context.directory, context.check
    url = params["url"]
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
        raise ValueError("仅支持不含账号密码的 HTTP/HTTPS 公开链接")
    downloader = []
    if settings().download_engine == "aria2c":
        connections = settings().download_connections
        downloader = [
            "--downloader",
            "http,https:aria2c",
            "--downloader-args",
            f"aria2c:-x{connections} -s{connections} -j1 -k1M --connect-timeout=10 --timeout=20 --max-tries=2",
        ]
    command(
        [
            "yt-dlp",
            "--ignore-config",
            "--no-playlist",
            "--js-runtimes",
            "node",
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
            format_selector(params.get("quality", "best")),
            "--merge-output-format",
            "mp4",
            "-o",
            "download.%(ext)s",
            *downloader,
            "--",
            url,
        ],
        directory,
        check,
        error_mapper=classify_error,
    )
    files = [p for p in directory.glob("download.*") if p.suffix not in {".part", ".ytdl"}]
    if len(files) != 1:
        raise ValueError("未取得完整媒体文件，此链接可能需要登录或没有所选清晰度")
    output = files[0]
    if output.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("合并后的视频超过 100 MB 上限")
    return ToolResult(output)
