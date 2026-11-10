#!/bin/sh
set -eu

# Only runs on the first startup of an empty Docker volume.
# psql quotes the password as an SQL literal; do not interpolate it into SQL.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 --set=app_password="$BADI_DB_PASSWORD" <<'SQL'
CREATE ROLE badi LOGIN PASSWORD :'app_password';
CREATE DATABASE badi OWNER badi;
SQL
