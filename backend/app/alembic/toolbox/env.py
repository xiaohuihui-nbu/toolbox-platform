from alembic import context

from app.toolbox.models.database import engine

with engine.connect() as connection:
    context.configure(connection=connection, version_table="tb_schema_version")
    with context.begin_transaction():
        context.run_migrations()
