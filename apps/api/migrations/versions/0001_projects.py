"""SPEC-0001 SP-01 project identity, grants, receipts and audit foundation.

This migration does not bootstrap real people or grant project access globally.
Migration user owns objects; runtime gets a deliberately narrower set of grants.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001_projects"
down_revision = None
branch_labels = None
depends_on = None


def _id(name: str = "id", *constraints: sa.ForeignKey) -> sa.Column[sa.Uuid]:
    return sa.Column(name, sa.Uuid(), *constraints, nullable=False)


def _timestamp(name: str, *, default: bool = True) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now() if default else None,
    )


def upgrade() -> None:
    op.create_table(
        "organizations",
        _id(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton"),
        sa.CheckConstraint("singleton IS TRUE", name="single_organization"),
    )
    op.create_table(
        "principals",
        _id(),
        _id("org_id", sa.ForeignKey("organizations.id")),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject"),
        sa.UniqueConstraint("org_id", "id"),
    )
    op.create_table(
        "global_grants",
        _id("principal_id", sa.ForeignKey("principals.id")),
        sa.Column("permission", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("principal_id", "permission"),
        sa.CheckConstraint("permission = 'project.create'", name="global_permission"),
    )
    op.create_table(
        "projects",
        _id(),
        _id("org_id", sa.ForeignKey("organizations.id")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        _id("created_by"),
        _timestamp("created_at"),
        sa.Column("acl_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "id"),
        sa.ForeignKeyConstraint(["org_id", "created_by"], ["principals.org_id", "principals.id"]),
        sa.CheckConstraint(
            "acl_revision BETWEEN 1 AND 9007199254740991", name="acl_revision_range"
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="project_name_length"),
        sa.CheckConstraint("char_length(description) <= 4000", name="project_description_length"),
    )
    op.create_index("ix_projects_order", "projects", ["created_at", "id"])
    op.create_table(
        "memberships",
        _id("project_id"),
        _id("principal_id"),
        _id("org_id"),
        sa.Column("role", sa.String(16), nullable=False),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("project_id", "principal_id"),
        sa.ForeignKeyConstraint(["org_id", "project_id"], ["projects.org_id", "projects.id"]),
        sa.ForeignKeyConstraint(["org_id", "principal_id"], ["principals.org_id", "principals.id"]),
        sa.CheckConstraint("role IN ('owner', 'editor', 'reader')", name="membership_role"),
    )
    op.create_index("ix_membership_principal", "memberships", ["principal_id", "project_id"])
    op.create_index(
        "ix_membership_order", "memberships", ["project_id", "created_at", "principal_id"]
    )
    op.create_table(
        "audit_events",
        _id(),
        _id("org_id"),
        _id("project_id"),
        _id("actor_id"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False, server_default="allowed"),
        _timestamp("occurred_at"),
        _id("request_id"),
        sa.Column("delta", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id", "project_id"], ["projects.org_id", "projects.id"]),
        sa.ForeignKeyConstraint(["org_id", "actor_id"], ["principals.org_id", "principals.id"]),
        sa.CheckConstraint("outcome = 'allowed'", name="audit_allowed_mutations"),
    )
    op.create_index("ix_audit_order", "audit_events", ["project_id", "occurred_at", "id"])
    op.create_table(
        "idempotency_receipts",
        _id("actor_id", sa.ForeignKey("principals.id")),
        _id("scope_id"),
        sa.Column("operation", sa.String(64), nullable=False),
        _id("key"),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id")),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("body", pg.JSONB(), nullable=False),
        sa.Column("headers", pg.JSONB(), nullable=False),
        _timestamp("created_at"),
        _timestamp("expires_at", default=False),
        sa.PrimaryKeyConstraint("actor_id", "scope_id", "operation", "key"),
        sa.CheckConstraint("status_code BETWEEN 200 AND 299", name="receipt_success"),
        sa.CheckConstraint("expires_at > created_at", name="receipt_ttl"),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="receipt_digest"),
    )
    op.create_index("ix_receipts_expiry", "idempotency_receipts", ["expires_at"])
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        _id("principal_id", sa.ForeignKey("principals.id")),
        sa.Column("csrf_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_ciphertext", sa.LargeBinary(), nullable=True),
        _timestamp("created_at"),
        _timestamp("last_seen_at"),
        _timestamp("expires_at", default=False),
        sa.CheckConstraint("expires_at > created_at", name="session_ttl"),
    )
    op.create_index("ix_sessions_expiry", "sessions", ["expires_at"])
    op.create_table(
        "oidc_flows",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("verifier_ciphertext", sa.LargeBinary(), nullable=False),
        _timestamp("created_at"),
        _timestamp("expires_at", default=False),
        sa.CheckConstraint("expires_at > created_at", name="oidc_flow_ttl"),
    )
    op.create_index("ix_oidc_flows_expiry", "oidc_flows", ["expires_at"])

    # No global grants/organization mutation, DDL, audit UPDATE/DELETE or ownership for runtime.
    op.execute("GRANT SELECT ON organizations, global_grants, alembic_version TO torii_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON principals, projects TO torii_runtime")
    op.execute("GRANT SELECT, INSERT ON audit_events TO torii_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON memberships, idempotency_receipts, "
        "sessions, oidc_flows TO torii_runtime"
    )


def downgrade() -> None:
    raise RuntimeError("Preserve history: restore to a new isolated database instead of downgrade")
