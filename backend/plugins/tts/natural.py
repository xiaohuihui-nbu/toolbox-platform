from app.toolbox.contracts.tools import ToolContext, ToolResult


def execute(context: ToolContext) -> ToolResult:
    params, directory, check = context.params, context.directory, context.check
    job_id, attempt = context.job_id, context.attempt
    from app.toolbox.providers.gptsovits import synthesize

    output = synthesize(params, directory, check, job_id, attempt)
    return ToolResult(output)
