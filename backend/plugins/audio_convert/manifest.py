from app.toolbox.schemas.tools import MediaInput

TOOLS = [
    {
        "id": "audio.extract",
        "name": "音频提取",
        "category": "音频工具",
        "icon": "Music2",
        "color": "violet",
        "description": "从音视频中提取音轨，转换为 MP3 文件。",
        "tags": ["FFmpeg", "MP3"],
        "mode": "job",
        "handler": "extract",
        "schema": MediaInput,
        "note": "支持常见音视频文件，单文件最大 100 MB。",
    }
]
