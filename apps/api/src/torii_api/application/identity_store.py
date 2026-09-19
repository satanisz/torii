"""SPEC-0001 B2a1 internal persistence, NOT an identity/token verifier.

Only a future trusted OIDC adapter may supply Identity values. There are no
HTTP routes, raw-claims parsing, network calls or implicit permission grants.
"""

import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, RowMapping, text

from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity
from torii_api.security.session_secrets import (
    SecretCodec,
    SecretDecodeError,
    new_token,
    token_hash,
)
from torii_api.storage.transactions import transaction

_IDLE = timedelta(minutes=30)
_ABSOLUTE = timedelta(hours=8)
_FLOW = timedelta(minutes=5)


@dataclass(frozen=True)
class Flow:
    state: str = field(repr=False)
    browser: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)


@dataclass(frozen=True)
class ConsumedFlow:
    nonce_hash: str = field(repr=False)
    verifier: str = field(repr=False)


@dataclass(frozen=True)
class Principal:
    principal_id: UUID
    display_name: str = field(repr=False)
    can_create_project: bool


@dataclass(frozen=True)
class NewSession:
    session_id: str = field(repr=False)
    csrf_token: str = field(repr=False)
    principal: Principal
    expires_at: datetime


@dataclass(frozen=True)
class ActiveSession:
    principal: Principal
    csrf_token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class RevokedSession:
    refresh_token: str | None = field(repr=False)
    secret_error: bool


def _now(conn: Connection) -> datetime:
    value: datetime = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    return value


def _principal(conn: Connection, identifier: UUID, issuer: str) -> Principal:
    # Deliberately NOT FOR UPDATE: auth locks only session, avoiding the inverse
    # of login's principal -> previous-session lock order.
    row = (
        conn.execute(
            text(
                "SELECT p.id,p.display_name,EXISTS(SELECT 1 FROM global_grants g "
                "WHERE g.principal_id=p.id AND g.permission='project.create') AS can_create "
                "FROM principals p WHERE p.id=:id AND p.active AND p.issuer=:issuer"
            ),
            {"id": identifier, "issuer": issuer},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise DomainError(401, "unauthorized")
    return Principal(row["id"], row["display_name"], row["can_create"])


def _session(conn: Connection, identifier: str) -> RowMapping:
    row = (
        conn.execute(
            text("SELECT * FROM sessions WHERE id_hash=:id FOR UPDATE"), {"id": identifier}
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise DomainError(401, "unauthorized")
    return row


def _opaque_from_storage(value: str) -> str:
    try:
        token_hash(value)
    except DomainError:
        raise SecretDecodeError() from None
    return value


class IdentityStore:
    def __init__(self, engine: Engine, codec: SecretCodec, trusted_issuer: str) -> None:
        # Configuration URL validation remains in Settings; this also rejects an
        # absent internal trust boundary without reflecting the supplied value.
        if not isinstance(trusted_issuer, str) or not trusted_issuer:
            raise DomainError(503, "identity_unavailable")
        self._engine = engine
        self._codec = codec
        self._issuer = trusted_issuer

    def create_flow(self) -> Flow:
        flow = Flow(new_token(), new_token(), new_token(), new_token())
        state_hash = token_hash(flow.state)
        encrypted = self._codec.seal("verifier", state_hash, flow.verifier)
        with transaction(self._engine) as conn:
            now = _now(conn)
            conn.execute(
                text(
                    "INSERT INTO oidc_flows(state_hash,browser_hash,nonce_hash,verifier_ciphertext,"
                    "created_at,expires_at) VALUES (:state,:browser,:nonce,:verifier,:now,:expires)"
                ),
                {
                    "state": state_hash,
                    "browser": token_hash(flow.browser),
                    "nonce": token_hash(flow.nonce),
                    "verifier": encrypted,
                    "now": now,
                    "expires": now + _FLOW,
                },
            )
            return flow

    def consume_flow(self, state: str, browser: str) -> ConsumedFlow:
        state_hash, browser_hash = token_hash(state), token_hash(browser)
        with transaction(self._engine) as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT * FROM oidc_flows WHERE state_hash=:state "
                        "AND browser_hash=:browser "
                        "FOR UPDATE"
                    ),
                    {"state": state_hash, "browser": browser_hash},
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["expires_at"] <= _now(conn):
                raise DomainError(401, "unauthorized")
            # Binding is also compared explicitly; never compare plaintext cookies in SQL/logs.
            if not hmac.compare_digest(row["browser_hash"], browser_hash):
                raise DomainError(401, "unauthorized")
            verifier = _opaque_from_storage(
                self._codec.open("verifier", state_hash, row["verifier_ciphertext"])
            )
            conn.execute(
                text("DELETE FROM oidc_flows WHERE state_hash=:state"), {"state": state_hash}
            )
            return ConsumedFlow(row["nonce_hash"], verifier)

    def _provision(self, conn: Connection, identity: Identity) -> UUID:
        if identity.issuer != self._issuer:
            raise DomainError(401, "unauthorized")
        org = conn.execute(text("SELECT id FROM organizations")).scalar_one_or_none()
        if org is None:
            raise DomainError(503, "identity_unavailable")
        principal: UUID | None = conn.execute(
            text(
                "INSERT INTO principals(id,org_id,issuer,subject,display_name,created_at) "
                "VALUES (:id,:org,:issuer,:subject,:display,clock_timestamp()) "
                "ON CONFLICT (issuer,subject) DO UPDATE SET display_name=EXCLUDED.display_name "
                "WHERE principals.active AND principals.org_id=EXCLUDED.org_id RETURNING id"
            ),
            {
                "id": uuid4(),
                "org": org,
                "issuer": identity.issuer,
                "subject": identity.subject,
                "display": identity.display_name,
            },
        ).scalar_one_or_none()
        if principal is None:
            raise DomainError(401, "unauthorized")
        return principal

    def provision_identity(self, identity: Identity) -> Principal:
        with transaction(self._engine) as conn:
            return _principal(conn, self._provision(conn, identity), self._issuer)

    def create_session(
        self,
        identity: Identity,
        previous_session: str | None = None,
        refresh_token: str | None = None,
    ) -> NewSession:
        identifier, csrf = new_token(), new_token()
        identifier_hash = token_hash(identifier)
        encrypted_csrf = self._codec.seal("csrf", identifier_hash, csrf)
        encrypted_refresh = (
            self._codec.seal("refresh", identifier_hash, refresh_token)
            if refresh_token is not None
            else None
        )
        previous_hash = None
        if previous_session is not None:
            try:
                previous_hash = token_hash(previous_session)
            except DomainError as exc:
                if exc.status != 401:
                    raise
                # An invalid old cookie cannot veto an independently verified login.
        with transaction(self._engine) as conn:
            principal_id = self._provision(conn, identity)
            if previous_hash is not None:
                conn.execute(
                    text("DELETE FROM sessions WHERE id_hash=:old"), {"old": previous_hash}
                )
            now = _now(conn)  # After principal/previous-session locks, not transaction start.
            expires = now + _ABSOLUTE
            conn.execute(
                text(
                    "INSERT INTO sessions(id_hash,principal_id,csrf_ciphertext,refresh_ciphertext,"
                    "created_at,last_seen_at,expires_at) VALUES (:id,:principal,:csrf,:refresh,"
                    ":now,:now,:expires)"
                ),
                {
                    "id": identifier_hash,
                    "principal": principal_id,
                    "csrf": encrypted_csrf,
                    "refresh": encrypted_refresh,
                    "now": now,
                    "expires": expires,
                },
            )
            return NewSession(
                identifier, csrf, _principal(conn, principal_id, self._issuer), expires
            )

    def authenticate_session(self, session_id: str) -> ActiveSession:
        identifier = token_hash(session_id)
        with transaction(self._engine) as conn:
            row = _session(conn, identifier)
            now = _now(conn)
            if row["expires_at"] <= now or row["last_seen_at"] <= now - _IDLE:
                raise DomainError(401, "unauthorized")
            principal = _principal(conn, row["principal_id"], self._issuer)
            csrf = _opaque_from_storage(
                self._codec.open("csrf", identifier, row["csrf_ciphertext"])
            )
            expires: datetime | None = conn.execute(
                text(
                    "UPDATE sessions SET last_seen_at=:now WHERE id_hash=:id "
                    "AND expires_at>:now AND last_seen_at>:idle RETURNING expires_at"
                ),
                {"now": now, "id": identifier, "idle": now - _IDLE},
            ).scalar_one_or_none()
            if expires is None:
                raise DomainError(401, "unauthorized")
            return ActiveSession(principal, csrf, expires)

    def revoke_session(self, session_id: str) -> RevokedSession:
        identifier = token_hash(session_id)
        with transaction(self._engine) as conn:
            row = _session(conn, identifier)
            refresh, secret_error = None, False
            if row["refresh_ciphertext"] is not None:
                try:
                    refresh = self._codec.open("refresh", identifier, row["refresh_ciphertext"])
                except SecretDecodeError:
                    secret_error = True  # Corruption must not prevent LOCAL revocation.
            conn.execute(text("DELETE FROM sessions WHERE id_hash=:id"), {"id": identifier})
            return RevokedSession(refresh, secret_error)

    def cleanup_expired(self, limit: int = 100) -> tuple[int, int]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError(422, "validation_failed", ("/limit",))
        with transaction(self._engine) as conn:
            flows = self._cleanup(conn, "oidc_flows", limit)
            sessions = self._cleanup(conn, "sessions", limit)
            return flows, sessions

    @staticmethod
    def _cleanup(conn: Connection, table: Literal["oidc_flows", "sessions"], limit: int) -> int:
        # Identifiers come only from the closed internal allowlist above, never request data.
        key = "state_hash" if table == "oidc_flows" else "id_hash"
        expired = "expires_at<=clock_timestamp()"
        if table == "sessions":
            expired += " OR last_seen_at<=clock_timestamp()-interval '30 minutes'"
        rows = list(
            conn.execute(
                text(
                    f"SELECT * FROM {table} WHERE ({expired}) ORDER BY expires_at,{key} "
                    "LIMIT :limit FOR UPDATE SKIP LOCKED"
                ),
                {"limit": limit},
            ).mappings()
        )
        count = 0
        for row in rows:
            now = _now(conn)
            if row["expires_at"] <= now or (
                table == "sessions" and row["last_seen_at"] <= now - _IDLE
            ):
                conn.execute(text(f"DELETE FROM {table} WHERE {key}=:id"), {"id": row[key]})
                count += 1
        return count
