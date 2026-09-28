from app.toolbox.schemas.tools import DownloadInput

TOOLS = [
    {
        "id": "video.download",
        "name": "视频下载",
        "category": "视频工具",
        "icon": "Download",
        "color": "blue",
        "description": "搜索公开视频或粘贴多个链接，批量下载并预览。",
        "tags": ["yt-dlp", "异步任务"],
        "mode": "job",
        "handler": "download",
        "schema": DownloadInput,
        "note": "支持 B站 / YouTube 搜索，每批最多 20 条；站点登录、区域或访问限制可能导致下载失败。",
    }
]
