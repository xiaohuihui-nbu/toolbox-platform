from pathlib import Path

from app.toolbox.config import settings
from app.toolbox.contracts.tools import ToolContext, ToolResult
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset
from app.toolbox.runtime.process import command
from app.toolbox.storage.s3 import client


def execute(context: ToolContext) -> ToolResult:
    params, directory, check = context.params, context.directory, context.check
    owner_id = context.owner_id
    with transaction() as db:
        asset = db.get(Asset, params["asset_id"])
        if not asset or asset.owner_id != owner_id:
            raise ValueError("输入文件不存在")
        source = directory / ("input" + Path(asset.name).suffix)
        client().download_file(settings().s3_bucket, asset.object_key, str(source))
    output = directory / "提取音频.mp3"
    command(["ffmpeg", "-nostdin", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source), "-vn", "-t", "600", "-codec:a", "libmp3lame", "-b:a", "192k", str(output)], directory, check)
    return ToolResult(output)
