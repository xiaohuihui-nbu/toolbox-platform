from app.toolbox.contracts.tools import ToolContext, ToolResult


def execute(context: ToolContext) -> ToolResult:
    params, directory = context.params, context.directory
    output = directory / "文本导出.txt"
    output.write_text(params["text"], encoding="utf-8")
    return ToolResult(output)
