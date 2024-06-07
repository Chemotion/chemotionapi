ELN_DB_PATH="${ELN_DB_PATH:-../../test_config}"
ELN_PATH="${ELN_PATH:-../../../chemotion_ELN}"

echo "Relative path to docker-compose.db.yml directory (ELN_DB_PATH): $ELN_DB_PATH"
ELN_DB_PATH="$(cd "$(dirname "${ELN_DB_PATH}")"; pwd)/$(basename "${ELN_DB_PATH}")"
echo "Absolute path to docker-compose.db.yml directory (ELN_DB_PATH): $ELN_DB_PATH"
echo "Relative path to CHEMOTION project (ELN_PATH): $ELN_PATH"
ELN_PATH="$(cd "$(dirname "${ELN_PATH}")"; pwd)/$(basename "${ELN_PATH}")"
echo "Absolute path to CHEMOTION project: $ELN_PATH"

cd $ELN_DB_PATH


if [ "$( PGPASSWORD=pass psql -h localhost -p 54320 -U postgres -XtAc "SELECT 1 FROM pg_database WHERE datname='chemotion_dev'" )" = '1' ]
then
    echo "Database available exists"
else
    docker-compose -f ./docker-compose.db.yml up -d
    sleep 2
    echo "Database not available pleas Check"
    exit 1
fi

PORT_NUMBER=3579



BASEDIR=$(dirname $0)
timestamp=$(date +%Y_%m_%d_%H_%M_%S_%N)
mkdir -p dumps

PGPASSWORD=pass pg_dump -h localhost -p 54320 -U postgres chemotion_dev > $PWD/dumps/$timestamp.sql
rm $PWD/dumps/latest.sql
ln -s $PWD/dumps/$timestamp.sql $PWD/dumps/latest.sql

echo "Backup (DB dump): $PWD/dumps/$timestamp.json"

PGPASSWORD=pass dropdb -h localhost -U postgres -p 54320 chemotion_dev -f --if-exists
echo "DB dropped: chemotion_dev"
PGPASSWORD=pass createdb -h localhost -U postgres -p 54320 chemotion_dev
echo "DB created: chemotion_dev"
PGPASSWORD=pass psql -o /dev/null -h localhost -U postgres -p 54320 -d chemotion_dev -f $BASEDIR/test.sql --quiet

echo "DB loaded: $BASEDIR/test.sql"

cd $ELN_PATH
. /home/martint/.asdf/asdf.sh
asdf shell ruby 2.7.8
ruby --version
ruby -x $ELN_PATH/bin/bundle exec ruby $ELN_PATH/bin/rails db:migrate

if lsof -Pi :$PORT_NUMBER -sTCP:LISTEN -t >/dev/null ; then
    lsof -i tcp:$PORT_NUMBER | awk 'NR!=1 {print $2}' | xargs -r kill
    echo "Chemotion is running (or port ${PORT_NUMBER} is used by another app)"
fi

cd $ELN_PATH
ELN_COMMAND="ruby -x $ELN_PATH/bin/bundle exec ruby -I./app/packs/src $ELN_PATH/bin/rails server -b 0.0.0.0 -p ${PORT_NUMBER} -e development"
echo RUN $ELN_COMMAND
ruby -x $ELN_PATH/bin/bundle exec ruby -I./app/packs/src $ELN_PATH/bin/rails server -b 0.0.0.0 -p ${PORT_NUMBER} -e development