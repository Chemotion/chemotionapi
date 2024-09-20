ELN_PATH="${ELN_PATH:-../../test_config}"

echo "Relative path to docker-compose.yml directory (ELN_PATH): ${ELN_PATH}"
ELN_PATH="$(cd "$(dirname "${ELN_PATH}")"; pwd)/$(basename "${ELN_PATH}")"
echo "Absolute path to docker-compose.yml directory (ELN_PATH): ${ELN_PATH}"


cd ${ELN_PATH}


if [ "$( PGPASSWORD=postgres psql -h localhost -p 54320 -U postgres -XtAc "SELECT 1 FROM pg_database WHERE datname='chemotion'" )" = '1' ]
then
    echo "Database available exists"
else
    echo "Make sure you have executed 'docker compose up' once in ${ELN_PATH}"
    docker compose start
    sleep 2
    echo "Database not available please Check"
    exit 1
fi

PORT_NUMBER=3579



BASEDIR=$(dirname $0)
timestamp=$(date +%Y_%m_%d_%H_%M_%S_%N)
mkdir -p dumps

PGPASSWORD=postgres pg_dump -h localhost -p 54320 -U postgres chemotion > $PWD/dumps/$timestamp.sql
rm $PWD/dumps/latest.sql
ln -s $PWD/dumps/$timestamp.sql $PWD/dumps/latest.sql

echo "Backup (DB dump): $PWD/dumps/$timestamp.json"

PGPASSWORD=postgres dropdb -h localhost -U postgres -p 54320 chemotion -f --if-exists
echo "DB dropped: chemotion"
PGPASSWORD=postgres createdb -h localhost -U postgres -p 54320 chemotion
echo "DB created: chemotion"
PGPASSWORD=postgres psql -o /dev/null -h localhost -U postgres -p 54320 -d chemotion -f $BASEDIR/test.sql --quiet

echo "DB loaded: $BASEDIR/test.sql"

RUNNING_ON_PORT=$(docker ps --filter "publish=3579" --format "{{.Names}}")


echo $RUNNING_ON_PORT
echo $($RUNNING_ON_PORT == "test_config-eln*")
if [[ $RUNNING_ON_PORT == test_config-eln* ]] ; then
    echo "Chemotion is running on port ${PORT_NUMBER}"
    cd ${ELN_PATH}
    docker compose exec eln bash -c "cd /chemotion/app & bundle exec ruby ./bin/rails db:migrate"
    echo "**SUCCESS**"
    exit 0
fi

echo "SHIT"

exit 3