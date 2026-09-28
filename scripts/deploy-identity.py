"""Quiesce, snapshot and migrate the FastapiAdmin toolbox; never delete business data.

Run after successful isolated rehearsal and building backend:0.2.0 + web.
The database snapshot and previous image IDs are retained under artifacts.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ['docker', 'compose', '--env-file', '.env', '-f', 'deploy/compose.yaml']
ARTIFACTS = ROOT / 'artifacts' / 'identity-adoption'


def run(args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


if __name__ == '__main__':
    # Existing API image checks its own pre-migration models, without exposing credentials.
    check = "from sqlalchemy import select,func; from app.toolbox.models.database import engine; from app.toolbox.models.entities import Job; c=engine.connect(); n=c.execute(select(func.count()).select_from(Job).where(Job.state.in_(['queued','running','cancel_requested','reconciling']))).scalar(); print(n); assert n==0, 'Wait for active jobs before adoption'"
    run(COMPOSE + ['exec', '-T', 'api', 'python', '-c', check])
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    ids = run(COMPOSE + ['ps', '-q'], capture_output=True, text=True).stdout.split()
    # Only IDs/config image/state, never dump full inspect containing secrets.
    images = run(['docker', 'inspect', '--format', '{{.Name}} {{.Image}}', *ids], capture_output=True, text=True).stdout
    (ARTIFACTS / f'previous-images-{stamp}.txt').write_text(images, encoding='utf-8')
    run(COMPOSE + ['stop', 'api'])
    try:
        # Check again after closing the submission endpoint, using the existing worker.
        run(COMPOSE + ['exec', '-T', 'worker', 'python', '-c', check])
    except Exception:
        run(COMPOSE + ['start', 'api'])
        raise
    run(COMPOSE + ['stop', 'worker', 'download-worker', 'provider-worker', 'dispatcher', 'search-worker'])
    backup = ARTIFACTS / f'cutover-{stamp}.sql'
    with backup.open('wb') as output:
        run(['docker', 'exec', 'toolbox-platform-mysql-1', 'sh', '-c',
             'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --no-tablespaces --set-gtid-purged=OFF toolbox'],
            stdout=output, stderr=subprocess.PIPE)
    assert backup.stat().st_size > 1000, 'Snapshot validation failed'
    run(COMPOSE + ['run', '--rm', '--no-deps', 'bootstrap'])
    run(COMPOSE + ['up', '-d', '--no-deps', 'api', 'worker', 'download-worker', 'provider-worker', 'dispatcher', 'search-worker', 'egress', 'tts-gateway', 'web'])
    print(json.dumps({'backup': str(backup), 'status': 'Services started; run acceptance checks.'}, ensure_ascii=False))
