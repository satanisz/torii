"""SPEC-0001 B1 receipts, used only within the caller's serialization lock."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import rfc8785
from sqlalchemy import Connection, text

from torii_api.domain.errors import DomainError


@dataclass(frozen=True)
class Result:
    """Explicit public DTO, not a database record or HTTP response envelope."""

    status_code: int
    body: dict[str, Any]
    headers: dict[str, str]


@dataclass(frozen=True)
class ReceiptKey:
    actor: UUID
    scope: UUID
    operation: str
    key: UUID

    def parameters(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "scope": self.scope,
            "operation": self.operation,
            "key": self.key,
        }

    def lock_create(self, conn: Connection) -> None:
        # Stable across processes/restarts. Collisions only serialize unrelated keys.
        value = rfc8785.dumps([str(self.actor), str(self.scope), self.operation, str(self.key)])
        lock_id = int.from_bytes(hashlib.sha256(value).digest()[:8], "big", signed=True)
        conn.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def fingerprint(method: str, path: str, if_match: str | None, body: object) -> str:
    return hashlib.sha256(
        rfc8785.dumps(
            {
                "method": method,
                "path": path,
                "if_match": if_match,
                "body": cast(Any, body),
            }
        )
    ).hexdigest()


_KEY_WHERE = "actor_id=:actor AND scope_id=:scope AND operation=:operation AND key=:key"


@dataclass(frozen=True)
class StoredReceipt:
    project_id: UUID
    fingerprint: str
    result: Result

    def replay(self, digest: str) -> Result:
        if self.fingerprint != digest:
            raise DomainError(409, "idempotency_conflict")
        return self.result


def find_receipt(conn: Connection, key: ReceiptKey) -> StoredReceipt | None:
    row = (
        conn.execute(
            text(
                "SELECT project_id, fingerprint, status_code, body, headers "
                "FROM idempotency_receipts "
                f"WHERE {_KEY_WHERE} AND expires_at > clock_timestamp()"
            ),
            key.parameters(),
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return StoredReceipt(
        row["project_id"],
        row["fingerprint"],
        Result(row["status_code"], row["body"], row["headers"]),
    )


def save_receipt(
    conn: Connection, key: ReceiptKey, digest: str, project_id: UUID, result: Result
) -> None:
    # An expired receipt can be replaced only while holding the same scope lock.
    conn.execute(
        text(
            f"DELETE FROM idempotency_receipts WHERE {_KEY_WHERE} "
            "AND expires_at <= clock_timestamp()"
        ),
        key.parameters(),
    )
    conn.execute(
        text(
            "INSERT INTO idempotency_receipts(actor_id,scope_id,operation,key,project_id,"
            "fingerprint,status_code,body,headers,created_at,expires_at) "
            "SELECT :actor,:scope,:operation,:key,:project,:digest,:status,CAST(:body AS jsonb),"
            "CAST(:headers AS jsonb),t,t+interval '24 hours' "
            "FROM (SELECT clock_timestamp() AS t) stamp"
        ),
        {
            **key.parameters(),
            "project": project_id,
            "digest": digest,
            "status": result.status_code,
            "body": json.dumps(result.body),
            "headers": json.dumps(result.headers),
        },
    )
