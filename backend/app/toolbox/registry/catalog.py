"""Only packaged manifests are discovered; no user-supplied Python import paths."""
import hashlib
import json
import re
from importlib import import_module
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins"
PLATFORM_ROOT = Path(__file__).resolve().parents[1]
shared_source = hashlib.sha256()
for area in ('contracts', 'runtime', 'providers', 'jobs', 'storage', 'schemas'):
    for source_path in sorted((PLATFORM_ROOT / area).rglob('*.py')):
        shared_source.update(source_path.relative_to(PLATFORM_ROOT).as_posix().encode())
        shared_source.update(source_path.read_bytes().replace(b'\r\n', b'\n'))
TOOLS, REGISTRY = [], {}
for path in sorted(PLUGIN_ROOT.glob("*/manifest.json")):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    package = path.parent.name
    if manifest["plugin_id"] != package or not re.fullmatch(r"[a-z][a-z0-9_]*", package) or manifest["sdk_version"] != 1:
        raise ValueError(f"Unsupported plugin manifest: {package}")
    source = hashlib.sha256()
    source.update(shared_source.digest())
    for module_path in sorted(path.parent.rglob('*.py')):
        source.update(module_path.relative_to(path.parent).as_posix().encode())
        source.update(module_path.read_bytes().replace(b'\r\n', b'\n'))
    for definition in manifest["tools"]:
        tool = dict(definition)
        if tool["id"] in REGISTRY or tool["mode"] not in {"browser", "request", "job"}:
            raise ValueError("Duplicate tool or unsupported execution mode")
        handler = tool.get("handler")
        if handler and not handler.startswith(f"plugins.{package}."):
            raise ValueError("Handler must belong to its reviewed plugin package")
        schema_ref = tool.pop("schema_ref", None)
        schema = None
        if schema_ref:
            module, name = schema_ref.split(":", 1)
            if not (module.startswith(f"plugins.{package}.") or module == "app.toolbox.schemas.tools"):
                raise ValueError("Schema must belong to its plugin or shared toolbox contracts")
            schema = getattr(import_module(module), name)
        if tool["mode"] != "browser" and (not handler or schema is None):
            raise ValueError("Server tool requires a handler and input schema")
        if tool["resource_profile"] not in {"browser", "download", "media_cpu", "provider_io", "maintenance"}:
            raise ValueError("Unknown resource profile")
        if not 1 <= tool['timeout_seconds'] <= 870 or not 0 < tool['max_output_bytes'] <= 2 * 1024**3:
            raise ValueError('Plugin execution budget exceeds the deployed worker limits')
        tool.update(schema=schema, plugin_id=package, plugin_version=manifest["version"])
        tool['implementation_hash'] = source.hexdigest()
        tool["schema_hash"] = hashlib.sha256(json.dumps(schema.model_json_schema() if schema else {}, sort_keys=True).encode()).hexdigest()
        TOOLS.append(tool); REGISTRY[tool["id"]] = tool


def public_tool(tool):
    return {**{key: value for key, value in tool.items() if key not in {"handler", "schema"}},
            "input_schema": tool["schema"].model_json_schema() if tool["schema"] else None}


REGISTRY_HASH = hashlib.sha256(json.dumps([public_tool(tool) for tool in TOOLS], sort_keys=True).encode()).hexdigest()
