"""SPEC-0002 readiness invariants; mocks are not PostgreSQL evidence."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from torii_api.storage.database import SCHEMA_HEAD, is_ready


@pytest.mark.parametrize(
    "revisions,expected",
    [
        ([(SCHEMA_HEAD,)], True),
        ([], False),
        ([("old",)], False),
        ([(SCHEMA_HEAD,), ("extra-head",)], False),
    ],
)
def test_readiness_exact_head_only(revisions: list[tuple[str]], expected: bool) -> None:
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value = revisions
    assert is_ready(engine) == expected


def test_readiness_connection_error() -> None:
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("private-query", {}, Exception("private-dsn"))
    assert is_ready(engine) is False
