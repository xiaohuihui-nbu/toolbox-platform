"""Compatibility HTTP contracts backed by FastapiAdmin services and sessions."""
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from app.core.dependencies import db_getter, redis_getter, get_current_user
from app.core.router_class import OperationLogRoute
from app.core.security import CustomOAuth2PasswordRequestForm
from app.modules.system.auth.service import LoginService
from app.modules.system.user.service import UserService
from app.modules.system.user.schema import UserCreateSchema, UserChangePasswordSchema
from app.toolbox.api.dependencies import administrator, current_user
from app.toolbox.config import settings
from app.toolbox.models.entities import UserProfile
from app.toolbox.models.identity import RoleModel
from app.toolbox.schemas.http import CreateUser, Login, PasswordChange, Preferences
from app.toolbox.services.presenters import user_data
from app.toolbox.services.identity import revoke_sessions

router = APIRouter(route_class=OperationLogRoute)


@router.post("/auth/login")
async def login(data: Login, response: Response, request: Request, db=Depends(db_getter, scope="function"), redis=Depends(redis_getter)):
    key = "tb:login:" + hashlib.sha256(data.username.encode()).hexdigest()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > 10:
        raise HTTPException(429, "尝试次数过多，请一分钟后重试")
    form = CustomOAuth2PasswordRequestForm(username=data.username, password=data.password,
        grant_type="password", scope="", client_id=None, client_secret=None,
        captcha_key="", captcha="", login_type="PC端")
    result = await LoginService.authenticate_user(request, redis, form, db)
    profile = await db.get(UserProfile, result.user_info["id"])
    response.set_cookie("fa_session", result.access_token, httponly=True,
        secure=settings().cookie_secure, samesite="strict", max_age=settings().session_hours * 3600)
    response.delete_cookie("tb_session")
    await redis.delete(key)
    request.state.toolbox_username = data.username
    return {**result.user_info, "is_admin": result.user_info["is_superuser"],
            "preferences": profile.preferences if profile else {}}


@router.post("/auth/logout")
async def logout(request: Request, response: Response, redis=Depends(redis_getter)):
    token = request.cookies.get("fa_session")
    if token:
        await LoginService.logout(redis, token)
    response.delete_cookie("fa_session")
    response.delete_cookie("tb_session")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return user_data(user)


@router.put("/me/preferences")
async def preferences(data: Preferences, user=Depends(current_user), db=Depends(db_getter, scope="function")):
    row = await db.get(UserProfile, user.id)
    if row:
        row.preferences = data.model_dump()
    else:
        db.add(UserProfile(user_id=user.id, preferences=data.model_dump()))
    return data


@router.put("/me/password")
async def change_password(data: PasswordChange, response: Response, auth=Depends(get_current_user),
                          db=Depends(db_getter, scope="function"), redis=Depends(redis_getter)):
    await UserService(auth, db).change_password(UserChangePasswordSchema(
        old_password=data.current_password, new_password=data.new_password,
        confirm_password=data.new_password))
    await db.flush()
    await revoke_sessions(redis, auth.user.id)
    response.delete_cookie("fa_session")
    return {"ok": True}


@router.post("/admin/users", status_code=201)
async def create_user(data: CreateUser, user=Depends(administrator), auth=Depends(get_current_user), db=Depends(db_getter, scope="function")):
    role_id = await db.scalar(select(RoleModel.id).where(RoleModel.code == "toolbox_member"))
    row = await UserService(auth, db).create(UserCreateSchema(
        username=data.username, name=data.name, password=data.password, role_ids=[role_id]))
    db.add(UserProfile(user_id=row.id, preferences={}))
    return {"id": row.id, "username": row.username, "name": row.name, "is_admin": False, "preferences": {}}
