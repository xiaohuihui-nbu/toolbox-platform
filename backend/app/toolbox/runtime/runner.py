from importlib import import_module
from pathlib import Path

from app.toolbox.contracts.tools import ToolContext, ToolResult



def run(handler, params, owner_id, directory: Path, check, job_id=None, attempt=None):
    from app.toolbox.registry.catalog import TOOLS
    if handler not in {tool.get("handler") for tool in TOOLS}:
        raise ValueError("工具处理器未注册")
    context = ToolContext(params, owner_id, directory, check, job_id, attempt)
    module, method = handler.split(":", 1)
    result = getattr(import_module(module), method)(context)
    check()
    if not isinstance(result, ToolResult) or not result.output.resolve().is_relative_to(directory.resolve()):
        raise ValueError("工具输出路径无效")
    if not result.output.is_file() or result.output.stat().st_size == 0:
        raise ValueError("工具未生成有效文件")
    return result.output
