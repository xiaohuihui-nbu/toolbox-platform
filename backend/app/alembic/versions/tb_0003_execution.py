"""Versioned plugins, attempts, durable events and dispatch leases."""
from alembic import op
import sqlalchemy as sa

revision = 'tb_0003_execution'
down_revision = 'tb_0002_identity'
branch_labels = None
depends_on = None


def upgrade():
    for name, kind, default in (
        ('plugin_id', sa.String(64), ''), ('plugin_version', sa.String(32), ''),
        ('schema_hash', sa.String(64), ''), ('resource_profile', sa.String(32), 'media_cpu'),
        ('stage', sa.String(32), 'queued')):
        op.add_column('tb_jobs', sa.Column(name, kind, nullable=False, server_default=default))
    op.add_column('tb_jobs', sa.Column('parent_job_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_tb_jobs_parent_job_id_tb_jobs', 'tb_jobs', 'tb_jobs', ['parent_job_id'], ['id'], ondelete='SET NULL')
    op.add_column('tb_jobs', sa.Column('config_snapshot', sa.JSON(), nullable=True))
    op.execute("UPDATE tb_jobs SET config_snapshot=JSON_OBJECT(), stage=state")
    op.alter_column('tb_jobs', 'config_snapshot', existing_type=sa.JSON(), nullable=False)
    op.create_table('tb_job_attempts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('tb_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempt_no', sa.Integer(), nullable=False), sa.Column('state', sa.String(24), nullable=False),
        sa.Column('lease_token', sa.String(36)), sa.Column('lease_until', sa.DateTime()),
        sa.Column('heartbeat_at', sa.DateTime()), sa.Column('started_at', sa.DateTime()),
        sa.Column('finished_at', sa.DateTime()), sa.Column('error_code', sa.String(64)),
        sa.Column('provider_job_id', sa.String(128)), sa.UniqueConstraint('job_id', 'attempt_no'))
    op.create_index('ix_tb_job_attempts_job_id', 'tb_job_attempts', ['job_id'])
    op.create_index('ix_tb_job_attempts_lease_until', 'tb_job_attempts', ['lease_until'])
    op.create_table('tb_job_events', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('tb_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempt_id', sa.String(36)), sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_tb_job_events_job_id', 'tb_job_events', ['job_id'])
    op.create_table('tb_worker_heartbeats', sa.Column('worker_id', sa.String(128), primary_key=True),
        sa.Column('resource_profile', sa.String(32), nullable=False), sa.Column('registry_hash', sa.String(64), nullable=False),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=False), sa.Column('expires_at', sa.DateTime(), nullable=False))
    op.create_index('ix_tb_worker_heartbeats_resource_profile', 'tb_worker_heartbeats', ['resource_profile'])
    op.create_index('ix_tb_worker_heartbeats_expires_at', 'tb_worker_heartbeats', ['expires_at'])
    for column in (sa.Column('attempt_id', sa.String(36)), sa.Column('not_before', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
                   sa.Column('lease_token', sa.String(36)), sa.Column('lease_until', sa.DateTime()),
                   sa.Column('deliveries', sa.Integer(), nullable=False, server_default='0')):
        op.add_column('tb_outbox', column)
    # Old terminal jobs remain readable with their original version marked as unrecorded.
    # Pending jobs cannot silently execute a newly deployed handler.
    op.execute("UPDATE tb_jobs SET state='failed', stage='failed', message='插件版本升级前未开始的任务，请检查参数后重新提交', finished_at=UTC_TIMESTAMP() WHERE state='queued'")
    op.execute("DELETE FROM tb_outbox WHERE job_id IN (SELECT id FROM tb_jobs WHERE state IN ('failed','cancelled','succeeded'))")


def downgrade():
    raise RuntimeError('Restore the pre-upgrade snapshot; execution history is not automatically dropped.')
