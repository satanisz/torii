#!/bin/sh
# SPEC-0020: separate tracking/auth roles and databases; passwords only via stdin.
set -eu
tracking_password="$(cat /run/secrets/postgres_tracking)"
auth_password="$(cat /run/secrets/postgres_auth)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE USER mlflow_tracking WITH PASSWORD '$tracking_password';
CREATE USER mlflow_auth WITH PASSWORD '$auth_password';
CREATE DATABASE mlflow_tracking OWNER mlflow_tracking;
CREATE DATABASE mlflow_auth OWNER mlflow_auth;
REVOKE CONNECT ON DATABASE mlflow_tracking FROM PUBLIC;
REVOKE CONNECT ON DATABASE mlflow_auth FROM PUBLIC;
GRANT CONNECT ON DATABASE mlflow_tracking TO mlflow_tracking;
GRANT CONNECT ON DATABASE mlflow_auth TO mlflow_auth;
EOSQL
