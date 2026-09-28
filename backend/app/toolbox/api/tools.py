from app.core.router_class import OperationLogRoute
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.toolbox.api.dependencies import administrator, current_user, require_tool
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import ToolSetting
from app.toolbox.registry.catalog import REGISTRY, TOOLS, public_tool
from app.toolbox.schemas.http import ToolToggle

router = APIRouter(route_class=OperationLogRoute)


@router.get('/tools/{tool_id}')
def tool_detail(tool_id: str, user=Depends(current_user)):
    require_tool(user, tool_id)
    tool = REGISTRY.get(tool_id)
    if not tool:
        raise HTTPException(404, '工具不存在')
    with transaction() as db:
        setting = db.get(ToolSetting, tool_id)
        enabled = not setting or setting.enabled
        if not enabled and not user.is_admin:
            raise HTTPException(404, '工具已停用')
        return {**public_tool(tool), 'enabled': enabled}


@router.get("/tools")
def tools(user=Depends(current_user)):
    with transaction() as db:
        flags = {t.tool_id: t.enabled for t in db.scalars(select(ToolSetting)).all()}
    return [{**public_tool(t), "enabled": flags.get(t["id"], True)} for t in TOOLS if user.is_admin or f"toolbox:tool:{t['id']}" in user.permissions]


@router.put("/admin/tools/{tool_id}")
def toggle_tool(tool_id: str, data: ToolToggle, user=Depends(administrator)):
    if tool_id not in REGISTRY:
        raise HTTPException(404, "工具不存在")
    with transaction() as db:
        row = db.get(ToolSetting, tool_id)
        if row:
            row.enabled = data.enabled
        else:
            db.add(ToolSetting(tool_id=tool_id, enabled=data.enabled))
    return {"ok": True}
