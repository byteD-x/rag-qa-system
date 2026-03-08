#!/bin/bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
SELECT 'CREATE DATABASE kb_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'kb_app')\gexec

SELECT 'CREATE DATABASE gateway_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gateway_app')\gexec
EOSQL
