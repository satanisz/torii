#!/bin/bash
set -euo pipefail
export KC_DB_PASSWORD="$(</run/secrets/postgres_identity)"
export KC_BOOTSTRAP_ADMIN_PASSWORD="$(</run/secrets/identity_admin)"
test -n "$KC_DB_PASSWORD" && test -n "$KC_BOOTSTRAP_ADMIN_PASSWORD"
exec /opt/keycloak/bin/kc.sh start --import-realm
