from app.toolbox.contracts.tools import ToolContext, ToolResult
from app.toolbox.runtime.process import command


def execute(context: ToolContext) -> ToolResult:
    params, directory, check = context.params, context.directory, context.check
    source = directory / "input.txt"
    source.write_text(params["text"], encoding="utf-8")
    output = directory / "语音合成.wav"
    command(
        ["espeak-ng", "-v", params["language"], "-s", str(params["speed"]), "-p", str(params.get("pitch", 50)), "-a", str(params.get("volume", 100)), "-f", str(source), "-w", str(output)],
        directory,
        check,
        timeout=180,
    )
    if params.get("format") == "mp3":
        converted = directory / "语音合成.mp3"
        command(["ffmpeg", "-nostdin", "-y", "-i", str(output), "-codec:a", "libmp3lame", "-b:a", "192k", str(converted)], directory, check)
        output = converted
    return ToolResult(output)
