from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Only the explicit Alembic head is acceptable; do not use create_all at startup.
SCHEMA_HEAD = "0001_projects"


def make_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=10000 -c lock_timeout=3000",
        },
    )


def is_ready(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            revisions = list(connection.execute(text("SELECT version_num FROM alembic_version")))
            return len(revisions) == 1 and revisions[0][0] == SCHEMA_HEAD
    except SQLAlchemyError:
        return False
