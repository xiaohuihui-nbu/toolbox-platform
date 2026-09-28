from pathlib import Path

from alembic import command
from alembic.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import User, UserProfile
from app.toolbox.models.identity import UserRolesModel, RoleModel
from app.toolbox.services.identity import seed_member_role
from app.toolbox.services.admin_ui import seed_admin_ui
from app.toolbox.storage.s3 import client
from app.utils.password_util import PwdUtil


def main():
    if len(settings().admin_password) < 8 or not settings().s3_secret_key:
        raise RuntimeError("请先生成部署密钥：scripts/start.ps1")
    cfg = Config(str(Path(__file__).resolve().parents[3] / "toolbox-alembic.ini"))
    command.upgrade(cfg, "head")
    command.upgrade(Config(str(Path(__file__).resolve().parents[3] / "alembic.ini")), "head")
    s3 = client()
    try:
        s3.head_bucket(Bucket=settings().s3_bucket)
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise
        s3.create_bucket(Bucket=settings().s3_bucket)
    with transaction() as db:
        if not db.scalar(select(User).where(User.username == "admin")):
            db.add(User(username="admin", name="管理员", password=PwdUtil.hash_password(settings().admin_password), is_superuser=True))
            db.flush()
        first_adoption = not db.scalar(select(RoleModel.id).where(RoleModel.code == "toolbox_member"))
        role_id = seed_member_role(db)
        seed_admin_ui(db)
        for user in db.scalars(select(User)).all():
            if not db.get(UserProfile, user.id):
                db.add(UserProfile(user_id=user.id, preferences={}))
            if first_adoption and not user.is_superuser and not db.scalar(select(UserRolesModel).where(UserRolesModel.user_id == user.id)):
                db.add(UserRolesModel(user_id=user.id, role_id=role_id))
    print("Toolbox schema, private bucket and initial administrator are ready.")


if __name__ == "__main__":
    main()
