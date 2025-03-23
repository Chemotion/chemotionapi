DOCKER_CWD="${DOCKER_CWD:-../../test_config}"
DOCKER_FILE="${DOCKER_FILE:-docker-compose.yml}"
DOCKER_COMPOSE_SERVICE="${DOCKER_COMPOSE_SERVICE:-eln}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-54320}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-chemotion}"
ELN_PORT="${ELN_PORT:-3579}"


echo "PG_PASSWORD $PG_PASSWORD"
echo "PG_HOST $PG_HOST"
echo "PG_PORT $PG_PORT"
echo "PG_USER $PG_USER"
echo "PG_DB $PG_DB"
echo "ELN_PORT $ELN_PORT"

echo "Relative path to docker-compose.yml directory (DOCKER_CWD): ${DOCKER_CWD}"
DOCKER_CWD="$(cd "$(dirname "${DOCKER_CWD}")"; pwd)/$(basename "${DOCKER_CWD}")"
echo "Absolute path to docker-compose.yml directory (DOCKER_CWD): ${DOCKER_CWD}"


cd ${DOCKER_CWD}


if [ "$( PGPASSWORD=$PG_PASSWORD psql -h $PG_HOST -p $PG_PORT -U $PG_USER -XtAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" )" = '1' ]
then
    echo "Database available exists"
else
    echo "Make sure you have executed 'docker compose up' once in ${DOCKER_CWD}"
    docker compose start
    sleep 2
    echo "Database not available please Check"
    exit 1
fi

PORT_NUMBER=$ELN_PORT



BASEDIR=$(dirname $0)
timestamp=$(date +%Y_%m_%d_%H_%M_%S_%N)
mkdir -p dumps

PGPASSWORD=$PG_PASSWORD pg_dump -h $PG_HOST -p $PG_PORT -U $PG_USER $PG_DB > $PWD/dumps/$timestamp.sql
rm $PWD/dumps/latest.sql
ln -s $PWD/dumps/$timestamp.sql $PWD/dumps/latest.sql

echo "Backup (DB dump): $PWD/dumps/$timestamp.json"

PGPASSWORD=postgres dropdb -h $PG_HOST -p $PG_PORT -U $PG_USER $PG_DB -f --if-exists
echo "DB dropped: chemotion"
PGPASSWORD=postgres createdb -h $PG_HOST -p $PG_PORT -U $PG_USER $PG_DB
echo "DB created: chemotion"
PGPASSWORD=postgres psql -o /dev/null -h $PG_HOST -p $PG_PORT -U $PG_USER -d $PG_DB -f $BASEDIR/test.sql --quiet

echo "DB loaded: $BASEDIR/test.sql"

# Sende eine GET-Anfrage und speichere die Cookies
# HTTP-Statuscode abrufen
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://0.0.0.0:${ELN_PORT}/mydb")
echo "Status code: $STATUS_CODE"
if [[ "$STATUS_CODE" -ne 404 ]]; then
    echo "Chemotion is running on port ${PORT_NUMBER}"
    cd ${DOCKER_CWD}
    echo "docker compose -f $DOCKER_FILE exec $DOCKER_COMPOSE_SERVICE bash -c 'exec rake db:migrate'"
    docker compose -f $DOCKER_FILE exec $DOCKER_COMPOSE_SERVICE bash -c "exec rake db:migrate"
    echo "**SUCCESS**"
    exit 0
fi

echo "SHIT"

exit 3