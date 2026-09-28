from app.toolbox.schemas.tools import TextInput

TOOLS = [
    {
        "id": "text.export",
        "name": "文本导出",
        "category": "文本工具",
        "icon": "FileText",
        "color": "green",
        "description": "将随手记录的内容保存为 UTF-8 文本文件。",
        "tags": ["UTF-8", "文件中心"],
        "mode": "job",
        "handler": "text",
        "schema": TextInput,
        "note": "用于验证插件、队列、任务与对象存储的完整执行链路。",
    }
]
