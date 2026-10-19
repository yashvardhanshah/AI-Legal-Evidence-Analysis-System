from alembic import context
from app.database import Base, get_engine
from app import models  # noqa: F401

target_metadata = Base.metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    from app.config import get_settings
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        migrate(supplied)
    else:
        with get_engine().connect() as connection:
            migrate(connection)
