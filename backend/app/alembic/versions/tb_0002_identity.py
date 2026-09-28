"""Adopt FastapiAdmin identity without deleting legacy data or object keys.

The old tb_schema_version chain is applied once by bootstrap before this first
upstream-chain revision. Subsequent toolbox migrations belong here exclusively.
"""
import json
import re
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'tb_0002_identity'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    if not sa.inspect(db).has_table('tb_jobs'):
        raise RuntimeError('Apply the frozen Toolbox 0001 baseline before adoption.')
    # Only this frozen schema is used. Never create_all against changing runtime models.
    for ddl in json.loads(Path(__file__).with_name('tb_0002_identity_schema.json').read_text(encoding='utf-8')):
        table_match = re.search(r'CREATE TABLE\s+`?(\w+)', ddl)
        index_match = re.search(r'CREATE (?:UNIQUE )?INDEX\s+(\w+)\s+ON\s+(\w+)', ddl)
        alter_match = re.search(r'ALTER TABLE\s+(\w+)\s+ADD CONSTRAINT\s+(\w+)', ddl)
        inspector = sa.inspect(db)
        if table_match and inspector.has_table(table_match[1]):
            continue
        if index_match and any(i['name'] == index_match[1] for i in inspector.get_indexes(index_match[2])):
            continue
        if alter_match and any(i['name'] == alter_match[2] for i in inspector.get_foreign_keys(alter_match[1])):
            continue
        op.execute(sa.text(ddl))

    legacy = 'tb_users' if sa.inspect(db).has_table('tb_users') else 'tb_users_legacy'
    users = db.execute(sa.text(f'SELECT * FROM {legacy} ORDER BY created_at,id')).mappings().all()
    for old in users:
        existing = db.execute(sa.text('SELECT id,uuid FROM sys_user WHERE username=:username'), {'username': old['username']}).mappings().first()
        if existing and existing['uuid'] != old['id']:
            raise RuntimeError('Identity collision: resolve existing sys_user before migration.')
        if len(old['name']) > 32:
            raise RuntimeError('Legacy display name exceeds upstream 32-character limit; resolve before migration.')
        if not existing:
            db.execute(sa.text('''INSERT INTO sys_user
                (uuid,username,password,name,is_superuser,status,is_deleted,created_time,updated_time,gender)
                VALUES (:uuid,:username,:password,:name,:superuser,:status,0,:created,:created,'2')'''),
                dict(uuid=old['id'], username=old['username'], password=old['password'], name=old['name'],
                     superuser=old['is_admin'], status=0 if old['enabled'] else 1, created=old['created_at']))
        user_id = db.scalar(sa.text('SELECT id FROM sys_user WHERE uuid=:uuid'), {'uuid': old['id']})
        if not db.scalar(sa.text('SELECT COUNT(*) FROM tb_user_profiles WHERE user_id=:id'), {'id': user_id}):
            prefs = old['preferences']
            db.execute(sa.text('INSERT INTO tb_user_profiles (user_id,legacy_id,preferences) VALUES (:id,:legacy,:prefs)'),
                       {'id': user_id, 'legacy': old['id'], 'prefs': prefs if isinstance(prefs, str) else json.dumps(prefs)})

    for table in ('tb_jobs', 'tb_assets'):
        columns = {c['name'] for c in sa.inspect(db).get_columns(table)}
        if 'legacy_owner_id' in columns:
            continue  # DDL may have committed before an interrupted deployment.
        if 'owner_sys_id' not in columns:
            op.add_column(table, sa.Column('owner_sys_id', sa.Integer(), nullable=True))
        db.execute(sa.text(f'UPDATE {table} t JOIN tb_user_profiles p ON t.owner_id=p.legacy_id SET t.owner_sys_id=p.user_id'))
        if db.scalar(sa.text(f'SELECT COUNT(*) FROM {table} WHERE owner_sys_id IS NULL')):
            raise RuntimeError('Unmapped task/file owner; no ownership conversion performed.')
        for fk in sa.inspect(db).get_foreign_keys(table):
            if fk['constrained_columns'] == ['owner_id']:
                op.drop_constraint(fk['name'], table, type_='foreignkey')
        for index in sa.inspect(db).get_indexes(table):
            if 'owner_id' in index['column_names']:
                op.drop_index(index['name'], table_name=table)
        # One ALTER keeps both column renames atomic; legacy ownership is retained for recovery.
        op.execute(sa.text(f'ALTER TABLE {table} CHANGE owner_id legacy_owner_id VARCHAR(36) NULL, CHANGE owner_sys_id owner_id INT NOT NULL'))

    for table, prefix in (('tb_jobs', 'job'), ('tb_assets', 'asset')):
        inspector = sa.inspect(db)
        if not any(f['constrained_columns'] == ['owner_id'] for f in inspector.get_foreign_keys(table)):
            op.create_foreign_key(f'fk_{table}_owner_id_sys_user', table, 'sys_user', ['owner_id'], ['id'])
        indices = {i['name'] for i in sa.inspect(db).get_indexes(table)}
        name = f'ix_tb_{prefix}_owner_created'
        if name not in indices:
            op.create_index(name, table, ['owner_id', 'created_at'])
        if table == 'tb_jobs' and 'uq_tb_jobs_owner_idempotency' not in indices:
            op.create_index('uq_tb_jobs_owner_idempotency', table, ['owner_id', 'idempotency_key'], unique=True)
    if sa.inspect(db).has_table('tb_users'):
        op.rename_table('tb_users', 'tb_users_legacy')


def downgrade():
    raise RuntimeError('Identity migration requires restoring the verified pre-migration backup; automatic destructive downgrade is disabled.')
