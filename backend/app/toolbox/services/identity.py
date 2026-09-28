"""Only toolbox preferences/permissions extend the upstream identity model."""
import json
from sqlalchemy import select

from app.common.enums import RedisInitKeyConfig
from app.toolbox.models.identity import RoleModel, MenuModel, UserRolesModel, RoleMenusModel
from app.toolbox.registry.catalog import TOOLS


def seed_member_role(db):
    role = db.scalar(select(RoleModel).where(RoleModel.code == "toolbox_member"))
    first_adoption = role is None
    if first_adoption:
        role = RoleModel(code="toolbox_member", name="工具箱成员", status=0, data_scope=1)
        db.add(role)
        db.flush()
    root = db.scalar(select(MenuModel).where(MenuModel.route_name == 'Toolbox'))
    if root is None:
        root = MenuModel(name="工具箱", title="工具箱", type=2, route_name="Toolbox",
                     route_path="/toolbox", component_path="toolbox/Workspace", order=10)
        db.add(root)
        db.flush()
    if first_adoption:
        db.add(RoleMenusModel(role_id=role.id, menu_id=root.id))
    for tool in TOOLS:
        existing = db.scalar(select(MenuModel.id).where(MenuModel.permission == f"toolbox:tool:{tool['id']}"))
        if existing:
            continue
        menu = MenuModel(name=tool["name"], title=tool["name"], type=3,
                         permission=f"toolbox:tool:{tool['id']}", parent_id=root.id)
        db.add(menu)
        db.flush()
        if first_adoption:
            db.add(RoleMenusModel(role_id=role.id, menu_id=menu.id))
    return role.id


async def revoke_sessions(redis, user_id):
    prefix = RedisInitKeyConfig.USER_SESSION.key
    async for key in redis.scan_iter(match=f"{prefix}:*"):
        raw = await redis.get(key)
        if not raw:
            continue
        record = json.loads(raw)
        if record.get("user_id") != user_id:
            continue
        session_id = record["session_id"]
        await redis.delete(key, f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}",
                           f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}")
