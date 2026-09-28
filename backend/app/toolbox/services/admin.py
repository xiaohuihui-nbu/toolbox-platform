"""Local administration; credentials are read from the container environment, never CLI arguments."""

import hashlib
import asyncio
import json
import sys

from redis import Redis
from sqlalchemy import select

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import User
from app.utils.password_util import PwdUtil


def reset_admin():
    password = settings().admin_password
    if len(password) < 8:
        raise ValueError("TB_ADMIN_PASSWORD 至少需要 8 位")
    with transaction() as db:
        user = db.scalar(select(User).where(User.username == "admin").with_for_update())
        if not user:
            raise ValueError("管理员账号尚未初始化")
        user.password = PwdUtil.hash_password(password)
        user.status = 0
        owner = user.id
    redis = Redis.from_url(settings().redis_url, decode_responses=True)
    for key in redis.scan_iter("tb:session:*"):
        if redis.get(key) == owner:
            redis.delete(key)
    redis.delete("tb:login:" + hashlib.sha256(b"admin").hexdigest())
    from app.common.enums import RedisInitKeyConfig
    prefix = RedisInitKeyConfig.USER_SESSION.key
    for key in redis.scan_iter(f"{prefix}:*"):
        raw = redis.get(key)
        if raw:
            record = json.loads(raw)
            if record.get("user_id") == owner:
                sid = record['session_id']
                redis.delete(key, f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{sid}", f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{sid}")
    print("Administrator password updated; previous sessions revoked.")


if __name__ == "__main__":
    if sys.argv[1:] != ["reset-admin"]:
        raise SystemExit("Usage: python -m app.toolbox.services.admin reset-admin")
    reset_admin()
