"""Real-service migration, unified authentication, RBAC and execution acceptance.

Run in the isolated rehearsal API container. Only own qa users/data are removed.
"""
import secrets
import time
from uuid import uuid4

import httpx
from sqlalchemy import select, text, delete

from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import User, UserProfile, Job, Asset, Outbox, ToolSetting
from app.toolbox.models.identity import RoleModel, MenuModel, UserRolesModel, RoleMenusModel
from app.toolbox.storage.s3 import client as s3

BASE = 'http://127.0.0.1:8000'
API = BASE + '/api/v1/toolbox'


def check(value, label):
    assert value, label
    print('PASS', label, flush=True)


def main():
    assert 'identity_rehearsal' in settings().database_url, 'Run only against the isolated rehearsal database'
    owners, custom_roles, custom_menus = [], [], []
    with transaction() as db:
        flag = db.get(ToolSetting, 'text.export')
        previous_flag = flag.enabled if flag else True
        if flag:
            flag.enabled = True
    admin = httpx.Client(timeout=30)
    try:
        check(admin.get(API + '/health').status_code == 200, 'API/SQL/Redis/S3 health')
        with transaction() as db:
            check(db.scalar(text('SELECT COUNT(*) FROM tb_users_legacy')) == db.scalar(text('SELECT COUNT(*) FROM tb_user_profiles WHERE legacy_id IS NOT NULL')), 'All legacy identities mapped')
            for table in ('tb_jobs', 'tb_assets'):
                check(db.scalar(text(f'SELECT COUNT(*) FROM {table} t LEFT JOIN tb_user_profiles p ON p.legacy_id=t.legacy_owner_id AND p.user_id=t.owner_id WHERE t.legacy_owner_id IS NOT NULL AND p.user_id IS NULL')) == 0, table + ' ownership preserved')
            check(db.scalar(text('SELECT COUNT(*) FROM tb_users_legacy l JOIN sys_user u ON u.uuid=l.id WHERE l.password<>u.password')) == 0, 'Password hashes preserved')
        r = admin.post(API + '/auth/login', json={'username': 'admin', 'password': settings().admin_password})
        check(r.status_code == 200 and 'fa_session' in admin.cookies, 'Existing administrator login uses upstream JWT cookie')
        check(admin.get(BASE + '/api/v1/system/user/current/info').status_code == 200, 'Same cookie authenticates upstream user endpoint')
        check(admin.get(BASE + '/api/v1/system/role/list').status_code == 200, 'Upstream role management available')
        check(admin.get(BASE + '/api/me').status_code == 200, 'Legacy HTTP compatibility')
        token_client = httpx.Client(timeout=30)
        r = token_client.post(BASE + '/api/v1/system/auth/login', data={'username': 'admin', 'password': settings().admin_password, 'login_type': 'PC端'})
        check(r.status_code == 200, 'Native FastapiAdmin login')
        token = r.json()['data']['access_token']
        check(token_client.get(API + '/me', headers={'Authorization': 'Bearer ' + token}).status_code == 200, 'Native token authenticates toolbox')
        member = httpx.Client(timeout=30)
        username, password = 'qa_' + secrets.token_hex(5), secrets.token_urlsafe(24)
        r = admin.post(API + '/admin/users', json={'username': username, 'name': '统一账号验收', 'password': password})
        check(r.status_code == 201, 'User created through upstream service')
        owner = r.json()['id']
        owners.append(owner)
        check(member.post(API + '/auth/login', json={'username': username, 'password': password}).status_code == 200, 'Member login')
        check(member.get(BASE + '/api/v1/system/role/list').status_code == 403, 'Member cannot manage roles')
        check(member.put(API + '/admin/tools/tts.basic', json={'enabled': False}).status_code == 403, 'Member cannot disable tools')
        prefs = {'mode': 'dark', 'accent': 'violet', 'favorites': ['json.format']}
        check(member.put(API + '/me/preferences', json=prefs).status_code == 200 and member.get(API + '/me').json()['preferences'] == prefs, 'Theme preferences use extension profile')
        check(member.post(API + '/jobs', headers={'Origin': 'https://unrelated.invalid', 'Idempotency-Key': str(uuid4())}, json={'tool_id': 'text.export', 'params': {'text': 'x'}}).status_code == 403, 'Cookie CSRF guard')
        with transaction() as db:
            role = RoleModel(name='验收隔离角色', code='qa_' + secrets.token_hex(5))
            db.add(role); db.flush(); custom_roles.append(role.id)
            db.execute(delete(UserRolesModel).where(UserRolesModel.user_id == owner))
            db.add(UserRolesModel(user_id=owner, role_id=role.id))
        check(member.get(API + '/tools').json() == [], 'Role removal hides unauthorized tools immediately')
        with transaction() as db:
            native_menu = MenuModel(name='验收原生权限', title='验收原生权限', type=3, permission='module_system:role:query')
            db.add(native_menu); db.flush(); custom_menus.append(native_menu.id)
            db.add(RoleMenusModel(role_id=custom_roles[0], menu_id=native_menu.id))
        check(member.get(BASE + '/api/v1/system/role/list').status_code == 200, 'Native permission grant takes effect without re-login')
        with transaction() as db: db.get(MenuModel, custom_menus[0]).is_deleted = True
        check(member.get(BASE + '/api/v1/system/role/list').status_code == 403, 'Soft-deleted native permission is immediately revoked')
        payload = {'tool_id': 'text.export', 'params': {'text': 'FastapiAdmin identity acceptance'}}
        check(member.post(API + '/jobs', headers={'Idempotency-Key': str(uuid4())}, json=payload).status_code == 403, 'Missing tool permission rejects submission')
        with transaction() as db:
            menu_id = db.scalar(select(MenuModel.id).where(MenuModel.permission == 'toolbox:tool:text.export'))
            db.add(RoleMenusModel(role_id=custom_roles[0], menu_id=menu_id))
        check(len(member.get(API + '/tools').json()) == 1, 'Grant tool permission without re-login')
        r = member.post(API + '/jobs', headers={'Idempotency-Key': str(uuid4())}, json=payload)
        check(r.status_code == 202, 'Authorized job accepted')
        job_id = r.json()['id']
        for _ in range(45):
            result = member.get(API + '/jobs/' + job_id).json()
            if result['state'] in ('succeeded', 'failed'):
                break
            time.sleep(1)
        check(result['state'] == 'succeeded', 'Real Celery/outbox task produces artifact with integer owner')
        assets = member.get(API + '/assets').json()
        check(len(assets) == 1 and member.get(API + '/assets/' + assets[0]['id'] + '/download').status_code == 200, 'Own artifact download')
        check(admin.get(API + '/assets/' + assets[0]['id']).status_code == 404, 'Owner isolation survives identity migration')
        with transaction() as db:
            db.get(User, owner).status = 1
        check(member.get(API + '/me').status_code == 401, 'Disabled user rejected on existing session')
        with transaction() as db:
            db.get(User, owner).status = 0
        new_password = secrets.token_urlsafe(24)
        r = member.put(API + '/me/password', json={'current_password': password, 'new_password': new_password})
        check(r.status_code == 200 and member.get(API + '/me').status_code == 401, 'Password change revokes session')
        check(member.post(API + '/auth/login', json={'username': username, 'password': new_password}).status_code == 200, 'New password accepted')
        time.sleep(1)
        with transaction() as db:
            check(db.scalar(text("SELECT COUNT(*) FROM sys_operation_log WHERE username=:name"), {'name': username}) > 0, 'Toolbox operations stored in upstream audit')
        check(admin.post(API + '/auth/logout').status_code == 200 and admin.get(API + '/me').status_code == 401, 'Logout invalidates shared session')
    finally:
        with transaction() as db:
            flag = db.get(ToolSetting, 'text.export')
            if flag:
                flag.enabled = previous_flag
            for owner in owners:
                for asset in db.scalars(select(Asset).where(Asset.owner_id == owner)).all():
                    s3().delete_object(Bucket=settings().s3_bucket, Key=asset.object_key)
                ids = select(Job.id).where(Job.owner_id == owner)
                db.execute(delete(Outbox).where(Outbox.job_id.in_(ids)))
                db.execute(delete(Asset).where(Asset.owner_id == owner))
                db.execute(delete(Job).where(Job.owner_id == owner))
                db.execute(delete(User).where(User.id == owner))
            for role_id in custom_roles:
                db.execute(delete(RoleModel).where(RoleModel.id == role_id))
            for menu_id in custom_menus:
                db.execute(delete(MenuModel).where(MenuModel.id == menu_id))


if __name__ == '__main__':
    main()
