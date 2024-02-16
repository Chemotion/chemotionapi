
dropdb -h localhost -U postgres -p 54320 chemotion_dev
createdb -h localhost -U postgres -p 54320 chemotion_dev
psql -h localhost -U postgres -p 54320 -d chemotion_dev -f latest.sql