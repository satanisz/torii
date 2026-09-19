#!/bin/sh
# SPEC-0002: runs only on an empty, dedicated PostgreSQL volume.
set -eu
# Generated hex credentials contain neither SQL quoting nor shell expansion.
migrator=$(cat /run/secrets/postgres_migrator)
runtime=$(cat /run/secrets/postgres_runtime)
identity=$(cat /run/secrets/postgres_identity)
for value in "$migrator" "$runtime" "$identity"; do
  case "$value" in *[!0-9a-f]*|'') echo 'Invalid provisioned credential' >&2; exit 1;; esac
  [ "${#value}" -eq 64 ] || exit 1
done
psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 <<SQL
CREATE ROLE torii_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '$migrator';
CREATE ROLE torii_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '$runtime';
CREATE ROLE torii_identity LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '$identity';
CREATE DATABASE torii_platform OWNER torii_migrator;
CREATE DATABASE torii_identity OWNER torii_identity;
REVOKE ALL ON DATABASE torii_platform FROM PUBLIC;
REVOKE ALL ON DATABASE torii_identity FROM PUBLIC;
GRANT CONNECT ON DATABASE torii_platform TO torii_runtime;
SQL
psql --username "$POSTGRES_USER" --dbname torii_platform --set ON_ERROR_STOP=1 <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO torii_runtime;
SQL
