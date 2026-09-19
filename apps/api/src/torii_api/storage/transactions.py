"""SPEC-0001 B1 transaction isolation and safe dependency failure boundary."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from torii_api.domain.errors import DomainError


@contextmanager
def transaction(engine: Engine, *, read_only: bool = False) -> Iterator[Connection]:
    try:
        with (
            engine.connect().execution_options(
                isolation_level="REPEATABLE READ" if read_only else "READ COMMITTED"
            ) as connection,
            connection.begin(),
        ):
            if read_only:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            yield connection
    except SQLAlchemyError:
        # Never attach SQL/parameters, credentials or database exception messages.
        # This catches failures on commit as well as execution; no success escapes.
        raise DomainError(503, "dependency_unavailable") from None
