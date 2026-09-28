"""Real MySQL/S3 acceptance; isolated rehearsal DB, dispatcher stopped.

The in-process publisher is replaced to inject broker failures without disturbing
the live broker. SQL transactions, execution claims, API auth and S3 are real.
"""
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.toolbox.api.dependencies import Principal
from app.toolbox.config import settings
from app.toolbox.jobs.capabilities import db_now
from app.toolbox.jobs.execution import run_job
from app.toolbox.jobs.outbox import dispatch_once
from app.toolbox.models.database import transaction
from app.toolbox.models.entities import Asset, Job, JobAttempt, JobEvent, Outbox, ToolSetting, User
from app.toolbox.schemas.http import JobInput, JobPatch
from app.toolbox.services.job_management import edit_job, remove_job
from app.toolbox.services.jobs import submit
from app.toolbox.storage.s3 import client


def check(value, label):
    assert value, label
    print('PASS', label, flush=True)


def main():
    assert 'identity_rehearsal' in settings().database_url
    created, objects = [], []
    with transaction() as db:
        admin = db.scalar(select(User).where(User.username == 'admin'))
        owner = Principal(admin.id, admin.username, admin.name, True)
        flag = db.get(ToolSetting, 'text.export')
        old_flag = flag.enabled if flag else True
        if flag: flag.enabled = True
        check(db.scalar(select(func.count()).select_from(Outbox)) == 0,
              'Rehearsal has no pending business deliveries')

    def create(text='execution acceptance'):
        result = submit(JobInput(tool_id='text.export', params={'text': text}), str(uuid4()), owner)
        created.append(result['id'])
        with transaction() as db:
            return result['id'], db.get(Job, result['id']).attempt

    try:
        with patch('app.toolbox.jobs.capabilities.REGISTRY_HASH', '0' * 64):
            try:
                create()
            except HTTPException as error:
                check(error.status_code == 503, 'Submission rejects workers with an incompatible deployment fingerprint')
            else: raise AssertionError('Incompatible worker accepted a new job')
        job_id, attempt = create()
        with transaction() as db:
            job = db.get(Job, job_id)
            check(job.plugin_id == 'demo_echo' and len(job.schema_hash) == 64
                  and db.get(JobAttempt, attempt) is not None
                  and db.get(Outbox, job_id).attempt_id == attempt,
                  'Submission persists version + attempt + outbox atomically')
        run_job(job_id, str(uuid4()))
        with transaction() as db:
            check(db.get(Job, job_id).state == 'queued', 'Unrelated attempt cannot claim job')
        run_job(job_id, attempt)
        run_job(job_id, attempt)
        with transaction() as db:
            rows = db.scalars(select(Asset).where(Asset.job_id == job_id)).all()
            check(db.get(Job, job_id).state == 'succeeded' and len(rows) == 1,
                  'Duplicate message creates exactly one committed artifact')
            objects.extend(a.object_key for a in rows)
            check(f'/attempts/{attempt}/' in rows[0].object_key, 'Immutable attempt-scoped object key')
            head = client().head_object(Bucket=settings().s3_bucket, Key=rows[0].object_key)
            check(len(head['Metadata']['sha256']) == 64, 'S3 artifact has verified checksum metadata')
            db.execute(delete(Outbox).where(Outbox.job_id == job_id))

        job_id, attempt = create()
        with transaction() as db: db.get(Job, job_id).plugin_version = '999.0.0'
        run_job(job_id, attempt)
        with transaction() as db:
            check(db.get(JobAttempt, attempt).error_code == 'VERSION_MISMATCH', 'Incompatible deployed plugin fails before execution')
            db.execute(delete(Outbox).where(Outbox.job_id == job_id))

        job_id, attempt = create('original input')
        result = edit_job(job_id, owner, JobPatch(params={'text': 'replacement input'}))
        created.append(result['id'])
        with transaction() as db:
            old, new = db.get(Job, job_id), db.get(Job, result['id'])
            check(old.params['text'] == 'original input' and old.state == 'cancelled'
                  and new.parent_job_id == old.id and new.params['text'] == 'replacement input',
                  'Editing queued input preserves immutable history and links replacement')
            db.execute(delete(Outbox).where(Outbox.job_id.in_([job_id, new.id])))
            new.state = 'cancelled'

        job_id, attempt = create()
        seen = []
        def unavailable(**kwargs):
            # A second transaction must be able to acquire the publication row now.
            with transaction() as other:
                row = other.scalar(select(Outbox).where(Outbox.job_id == job_id).with_for_update(nowait=True))
                seen.append(row.deliveries)
            raise ConnectionError('injected broker outage')
        with patch('app.toolbox.jobs.outbox.execute.apply_async', side_effect=unavailable): dispatch_once()
        with transaction() as db:
            item = db.get(Outbox, job_id)
            check(seen == [1] and item.deliveries == 1 and item.lease_until is None
                  and item.not_before > db_now(db), 'Broker failure occurs outside DB transaction and backs off durably')
            item.lease_until = db_now(db) - timedelta(seconds=1)
            item.lease_token = 'abandoned-publisher'
            item.not_before = db_now(db) - timedelta(seconds=1)
        sent = []
        with patch('app.toolbox.jobs.outbox.execute.apply_async', side_effect=lambda **kw: sent.append(kw)): dispatch_once()
        check(len(sent) == 1 and sent[0]['args'] == [job_id, attempt]
              and sent[0]['queue'] == 'toolbox.media_cpu', 'Abandoned publisher lease recovers on resource queue')
        with transaction() as db:
            row = db.get(Outbox, job_id); row.deliveries = 8; row.not_before = db_now(db) - timedelta(seconds=1)
        with patch('app.toolbox.jobs.outbox.execute.apply_async') as publisher:
            dispatch_once()
            check(not publisher.called, 'Exhausted deliveries do not publish again')
        with transaction() as db:
            check(db.get(JobAttempt, attempt).error_code == 'DISPATCH_EXHAUSTED'
                  and db.get(Outbox, job_id) is None, 'Bounded delivery failure is recorded')

        job_id, attempt = create()
        def expire_before_result(handler, params, owner_id, directory, *args):
            with transaction() as db:
                db.get(JobAttempt, attempt).lease_until = db_now(db) - timedelta(seconds=1)
            path = Path(directory) / 'expired.txt'; path.write_text('must not commit')
            return path
        with patch('app.toolbox.jobs.execution.run', side_effect=expire_before_result): run_job(job_id, attempt)
        with transaction() as db:
            check(db.scalar(select(func.count()).select_from(Asset).where(Asset.job_id == job_id)) == 0,
                  'Expired worker cannot commit an output')
        remaining = client().list_objects_v2(Bucket=settings().s3_bucket,
                                             Prefix=f'users/{owner.id}/jobs/{job_id}/').get('KeyCount', 0)
        check(remaining == 0, 'Rejected output is compensated in S3')
        with patch('app.toolbox.jobs.outbox.execute.apply_async'): dispatch_once()
        with transaction() as db:
            check(db.get(Job, job_id).state == 'failed' and db.get(JobAttempt, attempt).error_code == 'WORKER_LOST',
                  'Expired worker lease is recovered without infinite restart')

        job_id, attempt = create()
        with transaction() as db:
            job = db.get(Job, job_id); job.state = 'running'; job.result = {'submission_state': 'accepted', 'provider_job_id': 'test-remote-id'}
            att = db.get(JobAttempt, attempt); att.state = 'running'; att.lease_until = db_now(db) - timedelta(seconds=1)
        with patch('app.toolbox.jobs.outbox.execute.apply_async'): dispatch_once()
        with transaction() as db:
            check(db.get(Job, job_id).state == 'reconciling', 'Uncertain remote effect enters reconciliation, not automatic retry')
        try:
            remove_job(job_id, owner.id)
        except HTTPException as error:
            check(error.status_code == 409, 'Unreconciled remote task cannot be deleted')
        else: raise AssertionError('Unreconciled job deleted')

        with httpx.Client(base_url='http://127.0.0.1:8000/api/v1/toolbox', timeout=15) as api:
            api.post('/auth/login', json={'username': 'admin', 'password': settings().admin_password}).raise_for_status()
            data = api.get(f'/jobs/{job_id}/events').json()
            check(data['events'][-1]['event_type'] == 'reconciling' and len(data['attempts']) == 1,
                  'Authenticated API exposes persisted attempt and event history')
            check(api.get(f'/jobs/{job_id}/events?after={data["events"][-1]["id"]}').json()['events'] == [],
                  'Event cursor resumes without duplicates')
    finally:
        with transaction() as db:
            objects.extend(db.scalars(select(Asset.object_key).where(Asset.job_id.in_(created))).all())
            db.execute(delete(Asset).where(Asset.job_id.in_(created)))
            db.execute(delete(Outbox).where(Outbox.job_id.in_(created)))
            db.execute(delete(Job).where(Job.id.in_(created)))
            flag = db.get(ToolSetting, 'text.export')
            if flag: flag.enabled = old_flag
        for key in set(objects): client().delete_object(Bucket=settings().s3_bucket, Key=key)


if __name__ == '__main__': main()
