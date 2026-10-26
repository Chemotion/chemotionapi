#!/bin/bash
# Reset the integration-test database from the committed seed (tests/data/test.sql),
# run pending migrations, and restart the ELN — fully self-contained: everything runs
# against the docker stack in test_config/ (started here if not already up). Host
# Postgres client tools are used when available; otherwise all DB commands go through
# `docker compose exec db`, so docker is the only hard requirement.
#
# Invoked by tests/conftest.py (NO_SETUP=0) with CWD tests/data; prints **SUCCESS**
# on the last line when the seeded instance is ready — the conftest waits for that marker.

DOCKER_CWD="${DOCKER_CWD:-../test_config}"
DOCKER_FILE="${DOCKER_FILE:-compose.yml}"
DOCKER_COMPOSE_SERVICE="${DOCKER_COMPOSE_SERVICE:-eln}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-54320}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-chemotion}"
ELN_PORT="${ELN_PORT:-3579}"

# Every connection setting above is env-overridable, and this script runs
# `DROP DATABASE ... WITH (FORCE)`. Pointed at anything other than the test_config stack, that is
# an unrecoverable mistake with no prompt in between, so anything off the default target has to be
# opted into explicitly.
if [ "$PG_HOST" != "localhost" ] && [ "$PG_HOST" != "127.0.0.1" ] \
   || [ "$PG_PORT" != "54320" ] || [ "$PG_DB" != "chemotion" ]; then
    if [ "$CONFIRM_DESTRUCTIVE_DB_RESET" != "yes" ]; then
        echo "ERROR: refusing to DROP DATABASE '$PG_DB' on $PG_HOST:$PG_PORT."
        echo "       This script is for the test_config stack (localhost:54320/chemotion) only."
        echo "       To override deliberately, set CONFIRM_DESTRUCTIVE_DB_RESET=yes."
        exit 1
    fi
    echo "WARNING: destructive reset of '$PG_DB' on $PG_HOST:$PG_PORT (explicitly confirmed)"
fi

BASEDIR="$(cd "$(dirname "$0")"; pwd)"
SEED="${BASEDIR}/test.sql"

echo "PG_HOST=$PG_HOST PG_PORT=$PG_PORT PG_USER=$PG_USER PG_DB=$PG_DB ELN_PORT=$ELN_PORT"
DOCKER_CWD="$(cd "${DOCKER_CWD}" 2>/dev/null && pwd)"
if [ -z "${DOCKER_CWD}" ]; then
    echo "ERROR: DOCKER_CWD does not exist"
    exit 1
fi
echo "Compose directory: ${DOCKER_CWD}"
cd "${DOCKER_CWD}" || exit 1

compose() {
    # --env-file: compose.yml declares no default images, and this script is run directly by
    # conftest.py as well as from `just`, so the values cannot come from the caller's shell.
    docker compose --env-file "${DOCKER_CWD}/images.env" -f "${DOCKER_FILE}" "$@"
}

# Ensure the stack is up (no-op if already running).
compose up -d || { echo "ERROR: docker compose up failed"; exit 1; }

# Route psql/pg_dump through host tools when present, else through the db container.
if command -v psql >/dev/null 2>&1; then
    echo "Using host Postgres client tools (${PG_HOST}:${PG_PORT})"
    run_psql()  { PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$@"; }
    run_dump()  { PGPASSWORD="$PG_PASSWORD" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DB"; }
else
    echo "Host psql not found; using 'docker compose exec db' instead"
    run_psql()  { compose exec -T db psql -U "$PG_USER" "$@"; }
    run_dump()  { compose exec -T db pg_dump -U "$PG_USER" "$PG_DB"; }
fi

# Wait for Postgres to accept connections.
for i in $(seq 1 60); do
    run_psql -XtAc "SELECT 1" >/dev/null 2>&1 && break
    [ "$i" = "60" ] && { echo "ERROR: Postgres did not become ready"; exit 1; }
    sleep 2
done
echo "Postgres is ready"

# Backup the current DB (if it exists) before dropping it.
mkdir -p "${BASEDIR}/dumps"
if [ "$(run_psql -XtAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'")" = "1" ]; then
    timestamp=$(date +%Y_%m_%d_%H_%M_%S_%N)
    run_dump > "${BASEDIR}/dumps/${timestamp}.sql"
    rm -f "${BASEDIR}/dumps/latest.sql"
    ln -s "${BASEDIR}/dumps/${timestamp}.sql" "${BASEDIR}/dumps/latest.sql"
    echo "Backup written: ${BASEDIR}/dumps/${timestamp}.sql"
fi

# Drop, recreate, and load the seed.
run_psql -c "DROP DATABASE IF EXISTS $PG_DB WITH (FORCE);" || exit 1
run_psql -c "CREATE DATABASE $PG_DB;" || exit 1
# ON_ERROR_STOP: psql otherwise carries on past a failed statement and still exits 0, so a
# seed that only half-loaded would print SUCCESS and hand the suite a partial database —
# surfacing much later as test failures a long way from the cause.
run_psql -v ON_ERROR_STOP=1 -q -o /dev/null -d "$PG_DB" < "$SEED" \
    || { echo "ERROR: seed load failed"; exit 1; }
echo "DB reset from seed: ${SEED}"

# Bring the schema up to the running server version (normally a no-op: the committed seed is
# already dumped at the current stack version; this covers stack upgrades).
compose exec -T "${DOCKER_COMPOSE_SERVICE}" bash -c "cd /chemotion/app && bundle exec rake db:migrate" \
    || { echo "ERROR: rake db:migrate failed"; exit 1; }
echo "Migrations completed"

# Restart the ELN so it reconnects to the fresh database, then wait for it.
compose restart "${DOCKER_COMPOSE_SERVICE}" || exit 1
for i in $(seq 1 120); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${ELN_PORT}/about" 2>/dev/null)
    [ "$code" = "200" ] && break
    [ "$i" = "120" ] && { echo "ERROR: ELN did not come up on port ${ELN_PORT}"; exit 1; }
    sleep 5
done
echo "Chemotion is running on port ${ELN_PORT}"
echo "**SUCCESS**"
exit 0
