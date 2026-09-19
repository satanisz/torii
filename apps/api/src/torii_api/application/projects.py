"""SPEC-0001 B1 project transactions. No HTTP exposure or authentication bypass.

The actor is supplied by a trusted identity adapter, never by a request body.
Every use case rechecks persisted authorization, including idempotent replays.
"""

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, RowMapping, text

from torii_api.domain.errors import DomainError
from torii_api.domain.policy import Capability, Member, Role, authorize, validate_members
from torii_api.domain.project_inputs import (
    idempotency_key,
    parse_policy,
    parse_project_create,
    validate_page,
)
from torii_api.domain.values import check_etag, etag
from torii_api.security.cursor import CursorSigner
from torii_api.storage.receipts import ReceiptKey, Result, find_receipt, fingerprint, save_receipt
from torii_api.storage.transactions import transaction

_PROJECT_PATH = "/api/v1/projects"
_PROJECT_SELECT = (
    "SELECT p.id,p.org_id,p.name,p.description,p.acl_revision,p.created_by,p.created_at,m.role "
    "FROM projects p JOIN memberships m ON m.project_id=p.id AND m.org_id=p.org_id "
    "WHERE m.principal_id=:actor AND p.org_id=:org"
)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _active_org(conn: Connection, actor: UUID) -> UUID:
    org: UUID | None = conn.scalar(
        text("SELECT org_id FROM principals WHERE id=:actor AND active"), {"actor": actor}
    )
    if org is None:
        raise DomainError(401, "unauthorized")
    return org


def _create_allowed(conn: Connection, actor: UUID) -> UUID:
    org = _active_org(conn, actor)
    allowed = conn.scalar(
        text(
            "SELECT 1 FROM global_grants WHERE principal_id=:actor AND permission='project.create'"
        ),
        {"actor": actor},
    )
    if allowed is None:
        raise DomainError(403, "forbidden")
    return org


def _project(
    conn: Connection, actor: UUID, project: UUID, capability: Capability = Capability.READ
) -> RowMapping:
    org = _active_org(conn, actor)
    row = (
        conn.execute(
            text(_PROJECT_SELECT + " AND p.id=:project"),
            {"actor": actor, "org": org, "project": project},
        )
        .mappings()
        .one_or_none()
    )
    authorize(Role(row["role"]) if row else None, capability)
    assert row is not None  # authorize(None) has already raised the safe 404.
    return row


def _project_dto(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "acl_revision": row["acl_revision"],
        "created_by": str(row["created_by"]),
        "created_at": _utc(row["created_at"]),
        "my_role": row["role"],
    }


def _members(conn: Connection, project: UUID) -> list[Member]:
    return [
        Member(row.principal_id, Role(row.role))
        for row in conn.execute(
            text(
                "SELECT principal_id,role FROM memberships WHERE project_id=:project "
                "ORDER BY principal_id"
            ),
            {"project": project},
        )
    ]


def _member_dtos(members: list[Member]) -> list[dict[str, str]]:
    return [
        {"principal_id": str(m.principal_id), "role": m.role}
        for m in sorted(members, key=lambda m: m.principal_id)
    ]


def _policy_result(project: UUID, revision: int, members: list[Member]) -> Result:
    return Result(
        200,
        {"project_id": str(project), "revision": revision, "members": _member_dtos(members)},
        {"ETag": etag("acl", project, revision)},
    )


def _audit(
    conn: Connection,
    org: UUID,
    project: UUID,
    actor: UUID,
    request_id: UUID,
    action: str,
    delta: dict[str, Any],
) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_events(id,org_id,project_id,actor_id,action,target_id,"
            "request_id,delta) "
            "VALUES (:id,:org,:project,:actor,:action,:project,:request,CAST(:delta AS jsonb))"
        ),
        {
            "id": uuid4(),
            "org": org,
            "project": project,
            "actor": actor,
            "action": action,
            "request": request_id,
            "delta": json.dumps(delta),
        },
    )


class ProjectService:
    def __init__(self, engine: Engine, cursors: CursorSigner) -> None:
        self._engine = engine
        self._cursors = cursors

    def create_project(
        self, actor: UUID, *, body: object, key: str | None, request_id: UUID
    ) -> Result:
        with transaction(self._engine) as conn:
            org = _create_allowed(conn, actor)
            name, description = parse_project_create(body)
            receipt_key = ReceiptKey(actor, org, "createProject", idempotency_key(key))
            digest = fingerprint("POST", _PROJECT_PATH, None, body)
            receipt_key.lock_create(conn)
            _create_allowed(conn, actor)
            receipt = find_receipt(conn, receipt_key)
            if receipt:
                _project(conn, actor, receipt.project_id)
                return receipt.replay(digest)
            project = uuid4()
            conn.execute(
                text(
                    "INSERT INTO projects(id,org_id,name,description,created_by) "
                    "VALUES (:id,:org,:name,:description,:actor)"
                ),
                {
                    "id": project,
                    "org": org,
                    "name": name,
                    "description": description,
                    "actor": actor,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO memberships(project_id,principal_id,org_id,role) "
                    "VALUES (:project,:actor,:org,'owner')"
                ),
                {"project": project, "actor": actor, "org": org},
            )
            _audit(
                conn,
                org,
                project,
                actor,
                request_id,
                "project.created",
                {"members": [{"principal_id": str(actor), "role": "owner"}]},
            )
            result = Result(
                201,
                _project_dto(_project(conn, actor, project)),
                {"Location": f"{_PROJECT_PATH}/{project}"},
            )
            save_receipt(conn, receipt_key, digest, project, result)
            return result

    def get_project(self, actor: UUID, project: UUID) -> Result:
        with transaction(self._engine, read_only=True) as conn:
            return Result(200, _project_dto(_project(conn, actor, project)), {})

    def get_policy(self, actor: UUID, project: UUID) -> Result:
        with transaction(self._engine, read_only=True) as conn:
            row = _project(conn, actor, project, Capability.ACCESS)
            return _policy_result(project, row["acl_revision"], _members(conn, project))

    def replace_policy(
        self,
        actor: UUID,
        project: UUID,
        *,
        body: object,
        key: str | None,
        if_match: str | None,
        request_id: UUID,
    ) -> Result:
        with transaction(self._engine) as conn:
            row = _project(conn, actor, project, Capability.ACCESS)
            conn.execute(
                text("SELECT id FROM projects WHERE id=:project AND org_id=:org FOR UPDATE"),
                {"project": project, "org": row["org_id"]},
            ).one()
            row = _project(conn, actor, project, Capability.ACCESS)
            members = parse_policy(body)
            receipt_key = ReceiptKey(actor, project, "replaceAccessPolicy", idempotency_key(key))
            # Syntax/required check without comparing to current version yet.
            check_etag(if_match, if_match if if_match is not None else "")
            digest = fingerprint("PUT", f"{_PROJECT_PATH}/{project}/access-policy", if_match, body)
            receipt = find_receipt(conn, receipt_key)
            if receipt:
                return receipt.replay(digest)
            check_etag(if_match, etag("acl", project, row["acl_revision"]))
            active_ids = set(
                conn.scalars(
                    text("SELECT id FROM principals WHERE org_id=:org AND active AND id=ANY(:ids)"),
                    {"org": row["org_id"], "ids": [m.principal_id for m in members]},
                )
            )
            validate_members(members, active_ids)
            old_members = _members(conn, project)
            revision = row["acl_revision"]
            if set(members) != set(old_members):
                if revision >= 9007199254740991:
                    raise DomainError(409, "revision_exhausted")
                conn.execute(
                    text(
                        "DELETE FROM memberships WHERE project_id=:project "
                        "AND NOT (principal_id=ANY(:ids))"
                    ),
                    {"project": project, "ids": [m.principal_id for m in members]},
                )
                for member in members:
                    conn.execute(
                        text(
                            "INSERT INTO memberships(project_id,principal_id,org_id,role) "
                            "VALUES (:project,:principal,:org,:role) "
                            "ON CONFLICT (project_id,principal_id) DO UPDATE SET role=EXCLUDED.role"
                        ),
                        {
                            "project": project,
                            "principal": member.principal_id,
                            "org": row["org_id"],
                            "role": member.role.value,
                        },
                    )
                revision += 1
                conn.execute(
                    text("UPDATE projects SET acl_revision=:revision WHERE id=:project"),
                    {"revision": revision, "project": project},
                )
                before, after = set(old_members), set(members)
                _audit(
                    conn,
                    row["org_id"],
                    project,
                    actor,
                    request_id,
                    "project.access_changed",
                    {
                        "before": _member_dtos(list(before - after)),
                        "after": _member_dtos(list(after - before)),
                    },
                )
            result = _policy_result(project, revision, members)
            save_receipt(conn, receipt_key, digest, project, result)
            return result

    def _marker(self, cursor: str | None, context: dict[str, str]) -> dict[str, Any]:
        if cursor is None:
            return {}
        values = self._cursors.verify(cursor, context, now=datetime.now(UTC))
        try:
            timestamp, identifier = datetime.fromisoformat(values[0]), UUID(values[1])
            if timestamp.tzinfo is None:
                raise ValueError("Unzoned marker")
            return {"after_time": timestamp, "after_id": identifier}
        except ValueError:
            raise DomainError(400, "invalid_cursor") from None

    def _page(
        self,
        items: list[dict[str, Any]],
        limit: int,
        context: dict[str, str],
        time_field: str,
        id_field: str,
    ) -> Result:
        next_cursor = None
        if len(items) > limit:
            last = items[limit - 1]
            next_cursor = self._cursors.issue(
                context, [last[time_field], last[id_field]], now=datetime.now(UTC)
            )
        return Result(200, {"items": items[:limit], "next_cursor": next_cursor}, {})

    def list_projects(
        self, actor: UUID, *, limit: int = 50, q: str | None = None, cursor: str | None = None
    ) -> Result:
        with transaction(self._engine, read_only=True) as conn:
            org = _active_org(conn, actor)
            validate_page(limit, q)
            context = {"actor": str(actor), "path": _PROJECT_PATH, "q": q or ""}
            marker = self._marker(cursor, context)
            sql = _PROJECT_SELECT
            parameters: dict[str, Any] = {"actor": actor, "org": org, "limit": limit + 1, **marker}
            if q is not None:
                sql += " AND p.name ILIKE :pattern ESCAPE '\\'"
                parameters["pattern"] = (
                    "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                )
            if marker:
                sql += " AND (p.created_at,p.id) > (:after_time,:after_id)"
            rows = conn.execute(text(sql + " ORDER BY p.created_at,p.id LIMIT :limit"), parameters)
            return self._page(
                [_project_dto(row) for row in rows.mappings()], limit, context, "created_at", "id"
            )

    def list_memberships(
        self, actor: UUID, project: UUID, *, limit: int = 50, cursor: str | None = None
    ) -> Result:
        return self._project_collection(actor, project, "memberships", limit, cursor)

    def list_audit(
        self, actor: UUID, project: UUID, *, limit: int = 50, cursor: str | None = None
    ) -> Result:
        return self._project_collection(actor, project, "audit", limit, cursor)

    def _project_collection(
        self,
        actor: UUID,
        project: UUID,
        collection: Literal["memberships", "audit"],
        limit: int,
        cursor: str | None,
    ) -> Result:
        with transaction(self._engine, read_only=True) as conn:
            _project(
                conn,
                actor,
                project,
                Capability.ACCESS if collection == "memberships" else Capability.AUDIT,
            )
            validate_page(limit, None)
            context = {"actor": str(actor), "path": f"{_PROJECT_PATH}/{project}/{collection}"}
            marker = self._marker(cursor, context)
            if collection == "memberships":
                sql = "SELECT project_id,principal_id,role,created_at FROM memberships"
                time_column, id_column = "created_at", "principal_id"
            else:
                sql = (
                    "SELECT id,project_id,actor_id,action,target_id,outcome,occurred_at,request_id "
                    "FROM audit_events"
                )
                time_column, id_column = "occurred_at", "id"
            sql += " WHERE project_id=:project"
            if marker:
                sql += f" AND ({time_column},{id_column}) > (:after_time,:after_id)"
            sql += f" ORDER BY {time_column},{id_column} LIMIT :limit"
            rows = conn.execute(text(sql), {"project": project, "limit": limit + 1, **marker})
            items = []
            for row in rows.mappings():
                item = {
                    key: str(value) if isinstance(value, UUID) else value
                    for key, value in row.items()
                }
                item[time_column] = _utc(row[time_column])
                if collection == "audit":
                    item["version_id"] = None  # SP-01 has no definition versions yet.
                items.append(item)
            return self._page(items, limit, context, time_column, id_column)
