"""Toolbox extension of the FastapiAdmin factory and identity infrastructure."""
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text


@asynccontextmanager
async def toolbox_lifespan(app):
    from app.core.database import async_engine
    from app.core.redis_crud import redis_connect
    from app.toolbox.models import identity
    async with async_engine.connect() as connection:
        await connection.execute(text("SELECT id FROM sys_user LIMIT 1"))
        await connection.execute(text("SELECT user_id FROM tb_user_profiles LIMIT 1"))
    await redis_connect(app, status=True)
    try:
        yield
    finally:
        await redis_connect(app, status=False)
        await async_engine.dispose()


def register_toolbox(app):
    from app.modules.system.auth.controller import AuthRouter
    from app.modules.system.user.controller import UserRouter
    from app.modules.system.role.controller import RoleRouter
    from app.modules.system.menu.controller import MenuRouter
    from app.modules.system.dept.controller import DeptRouter
    from app.modules.system.position.controller import PositionRouter
    from app.modules.system.log.controller import LogRouter
    from app.modules.system.dict.controller import DictRouter
    from app.modules.system.params.controller import ParamsRouter
    from app.toolbox.api import accounts, assets, downloads, health, jobs, providers, search, tools

    system = APIRouter(prefix="/api/v1/system")
    for router in (AuthRouter, UserRouter, RoleRouter, MenuRouter, DeptRouter, PositionRouter, LogRouter, DictRouter, ParamsRouter):
        system.include_router(router)
    app.include_router(system)
    for module in (accounts, tools, jobs, assets, providers, search, downloads, health):
        app.include_router(module.router, prefix="/api/v1/toolbox")
        app.include_router(module.router, prefix="/api", include_in_schema=False)

    @app.middleware("http")
    async def csrf_guard(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "请求来源不匹配"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response
