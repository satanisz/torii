"""Run inside the isolated API container with its runtime credentials.

SPEC-0002 AC-03, SPEC-0001 storage boundary. Read-only catalogue assertions plus
rolled-back forbidden statements. No fixture inserts or destructive cleanup.
This is NOT a substitute for project transaction/restart/restore tests.
"""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from torii_api.config import database_url
from torii_api.storage.database import SCHEMA_HEAD, is_ready, make_engine


def check() -> None:
    if not __debug__:
        raise RuntimeError("Database checks require assertions; do not use python -O")
    engine = make_engine(database_url())
    try:
        if not is_ready(engine):
            raise AssertionError("Expected migrated platform database")
        with engine.connect() as conn:
            user = conn.scalar(text("SELECT current_user"))
            assert user == "torii_runtime", "Checks must use the runtime role"
            role = conn.execute(
                text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            ).one()
            assert tuple(role) == (False, False, False)
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_HEAD
            for relation in (
                "organizations",
                "global_grants",
                "principals",
                "projects",
                "memberships",
                "audit_events",
                "sessions",
                "oidc_flows",
                "idempotency_receipts",
            ):
                assert (
                    conn.scalar(
                        text("SELECT has_table_privilege(current_user, :relation, 'SELECT')"),
                        {"relation": relation},
                    )
                    is True
                )
            for relation, privilege in [
                ("audit_events", "UPDATE"),
                ("audit_events", "DELETE"),
                ("global_grants", "INSERT"),
                ("organizations", "INSERT"),
                ("alembic_version", "UPDATE"),
            ]:
                assert (
                    conn.scalar(
                        text("SELECT has_table_privilege(current_user, :relation, :privilege)"),
                        {"relation": relation, "privilege": privilege},
                    )
                    is False
                )
            assert (
                conn.scalar(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')"))
                is False
            )
            assert (
                conn.scalar(
                    text("SELECT has_database_privilege(current_user, 'torii_identity', 'CONNECT')")
                )
                is False
            )
            conn.rollback()
            for statement in (
                "UPDATE audit_events SET outcome='allowed' WHERE false",
                "DELETE FROM audit_events WHERE false",
                "CREATE TABLE public.torii_forbidden_ddl_probe(id integer)",
            ):
                denied = False
                try:
                    conn.execute(text(statement))
                except DBAPIError as exc:
                    denied = getattr(exc.orig, "sqlstate", None) == "42501"
                finally:
                    conn.rollback()
                assert denied, "Runtime must not edit audit or create business tables"
        print(
            "PASS PostgreSQL runtime: exact schema, least-privilege role, table grants, "
            "audit UPDATE/DELETE denied, DDL denied, IdP database isolated"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    check()
