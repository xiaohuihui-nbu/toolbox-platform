from dataclasses import dataclass, field
from fastapi import Depends, HTTPException, Request
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, db_getter
from app.modules.system.auth.service import LoginService
from app.modules.system.role.model import RoleModel
from app.toolbox.config import settings
from app.toolbox.models.entities import User, UserProfile

redis = Redis.from_url(settings().redis_url, decode_responses=True)


@dataclass(frozen=True)
class Principal:
    id: int
    username: str
    name: str
    is_admin: bool
    preferences: dict = field(default_factory=dict)
    permissions: frozenset[str] = frozenset()


async def current_user(request: Request, auth=Depends(get_current_user), db=Depends(db_getter, scope="function")):
    # Reload role permissions so disabling a role/menu takes effect without re-login.
    user = await db.scalar(select(User).where(User.id == auth.user.id).options(
        selectinload(User.roles).selectinload(RoleModel.menus)))
    if not user or user.is_deleted or user.status != 0:
        raise HTTPException(401, "请先登录")
    profile = await db.get(UserProfile, user.id)
    permissions, _ = LoginService._collect_permissions(user)
    request.state.toolbox_username = user.username
    return Principal(user.id, user.username, user.name, user.is_superuser,
                     profile.preferences if profile else {}, frozenset(permissions))


def administrator(user=Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return user


def require_tool(user, tool_id):
    if not user.is_admin and f"toolbox:tool:{tool_id}" not in user.permissions:
        raise HTTPException(403, "没有此工具的使用权限")
