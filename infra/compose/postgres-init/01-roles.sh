#!/bin/sh
# Creates the CreatorIQX roles and databases on first container start (ADR 0002).
#
#   creatoriqx_owner  owns the schema; used only by migrations
#   creatoriqx_app    runtime role: NOBYPASSRLS, owns nothing, cannot run DDL
#
# Passwords arrive as environment variables and are passed to psql as
# variables (:'name'), so they are never spliced into SQL text.
set -eu

: "${CIQX_OWNER_PASSWORD:?CIQX_OWNER_PASSWORD must be set}"
: "${CIQX_APP_PASSWORD:?CIQX_APP_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$CIQX_OWNER_PASSWORD" -v app_pw="$CIQX_APP_PASSWORD" <<'SQL'
CREATE ROLE creatoriqx_owner LOGIN PASSWORD :'owner_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE creatoriqx_app LOGIN PASSWORD :'app_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE DATABASE creatoriqx OWNER creatoriqx_owner;
CREATE DATABASE creatoriqx_test OWNER creatoriqx_owner;
SQL

for db in creatoriqx creatoriqx_test; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -v db="$db" <<'SQL'
-- Only the two CreatorIQX roles may connect.
REVOKE CONNECT, TEMPORARY ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO creatoriqx_owner, creatoriqx_app;

-- The owner role owns the schema; the app role may use it but not create in it.
ALTER SCHEMA public OWNER TO creatoriqx_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO creatoriqx_app;

-- Tables and sequences the owner creates later are usable (not alterable) by the app.
ALTER DEFAULT PRIVILEGES FOR ROLE creatoriqx_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO creatoriqx_app;
ALTER DEFAULT PRIVILEGES FOR ROLE creatoriqx_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO creatoriqx_app;
SQL
done

echo "CreatorIQX roles and databases created."
