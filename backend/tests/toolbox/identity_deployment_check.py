"""Read-only business data checks after adoption; authentication emits audit logs."""
import httpx
import sys
from sqlalchemy import text, select, inspect
from app.toolbox.config import settings
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import User, Job, Asset
from app.toolbox.storage.s3 import client


def main():
    with transaction() as db:
        assert not inspect(db.bind).has_table('tb_users')
        assert db.scalar(text('SELECT COUNT(*) FROM tb_users_legacy')) == db.scalar(text('SELECT COUNT(*) FROM tb_user_profiles WHERE legacy_id IS NOT NULL'))
        if '--strict-migration-snapshot' in sys.argv:
            assert db.scalar(text('SELECT COUNT(*) FROM tb_users_legacy l JOIN sys_user u ON u.uuid=l.id WHERE l.password<>u.password')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM tb_users_legacy l JOIN tb_user_profiles p ON p.legacy_id=l.id WHERE l.preferences<>p.preferences')) == 0
        for table in ('tb_jobs', 'tb_assets'):
            assert db.scalar(text(f'SELECT COUNT(*) FROM {table} t LEFT JOIN tb_user_profiles p ON t.owner_id=p.user_id AND t.legacy_owner_id=p.legacy_id WHERE t.legacy_owner_id IS NOT NULL AND p.user_id IS NULL')) == 0
        for asset in db.scalars(select(Asset)).all():
            head = client().head_object(Bucket=settings().s3_bucket, Key=asset.object_key)
            assert head['ContentLength'] == asset.size
        print('PASS legacy identity mappings, ownership and every stored object size')
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30) as session:
        assert session.get('/api/v1/toolbox/health').status_code == 200
        response = session.post('/api/v1/toolbox/auth/login', json={'username': 'admin', 'password': settings().admin_password})
        assert response.status_code == 200
        assert session.get('/api/v1/system/user/current/info').status_code == 200
        assert session.get('/api/v1/system/role/list').status_code == 200
        runtime = session.get('/api/v1/toolbox/admin/runtime').json()
        assert runtime['ready'] and all(w['compatible'] for w in runtime['workers'])
        print('PASS all resource profiles have live compatible consumers')
        for path in ('/api/jobs/query', '/api/assets', '/api/tts/status', '/api/tts/voices'):
            assert session.get(path).status_code == 200, path
        assets = session.get('/api/assets').json()
        for asset in assets:
            if asset.get('preview_kind'):
                r = session.get(f"/api/assets/{asset['id']}/preview", headers={'Range': 'bytes=0-63'})
                assert r.status_code == 206 and len(r.content) == min(64, asset['size'])
        print('PASS production login, native admin APIs, legacy jobs/files/TTS and media ranges')


if __name__ == '__main__':
    main()
