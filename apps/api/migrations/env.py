"""Migration credentials are independent of runtime/OIDC configuration."""

from alembic import context

from torii_api.config import database_url
from torii_api.storage.database import make_engine

if context.is_offline_mode():
    raise RuntimeError("Offline migration is not supported; use an isolated PostgreSQL database")

engine = make_engine(database_url())
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
