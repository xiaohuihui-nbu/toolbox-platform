from app.toolbox.storage.media import PREVIEW_MIMES


def user_data(user):
    return {"id": user.id, "username": user.username, "name": user.name, "is_admin": user.is_admin, "preferences": user.preferences}


def job_data(job):
    return {key: getattr(job, key) for key in ("id", "tool_id", "title", "state", "stage", "progress", "message", "result", "created_at", "started_at", "finished_at", "parent_job_id", "tool_version", "plugin_id", "plugin_version", "schema_hash")}


def asset_data(asset):
    return {**{key: getattr(asset, key) for key in ("id", "name", "size", "mime", "job_id", "created_at")}, "preview_kind": PREVIEW_MIMES.get(asset.mime)}
