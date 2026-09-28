"""Read-only production snapshot and isolated identity migration rehearsal.

Run from project root using backend/.venv/Scripts/python.exe. Backups contain
private data: artifacts is ignored by Git and Docker; do not publish it.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'identity-adoption'
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def run(args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def mysql(sql, database=None):
    command = 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' + (f' {database}' if database else '')
    return run(['docker', 'exec', '-i', 'toolbox-platform-mysql-1', 'sh', '-c', command], input=sql, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


if __name__ == '__main__':
    # Refuse to overwrite an earlier rehearsal database or backup.
    exists = mysql(b"SELECT SCHEMA_NAME FROM information_schema.schemata WHERE SCHEMA_NAME='toolbox_identity_rehearsal'")
    if b'toolbox_identity_rehearsal' in exists.stdout:
        raise SystemExit('Rehearsal database already exists; inspect it instead of overwriting it.')
    snapshot = ARTIFACTS / f'pre-adoption-{datetime.now():%Y%m%d-%H%M%S}.sql'
    with snapshot.open('wb') as output:
        run(['docker', 'exec', 'toolbox-platform-mysql-1', 'sh', '-c',
             'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --no-tablespaces --set-gtid-purged=OFF toolbox'],
            stdout=output, stderr=subprocess.PIPE)
    if snapshot.stat().st_size < 1000:
        raise RuntimeError('Unexpectedly small snapshot; clone not started.')
    mysql(b"CREATE DATABASE toolbox_identity_rehearsal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON toolbox_identity_rehearsal.* TO 'toolbox'@'%';")
    mysql(snapshot.read_bytes(), 'toolbox_identity_rehearsal')
    print(json.dumps({'snapshot': str(snapshot), 'bytes': snapshot.stat().st_size,
                      'clone': 'toolbox_identity_rehearsal'}, ensure_ascii=False))
