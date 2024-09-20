#!/bin/fish


set p "$(status --current-filename)"
set p "$(dirname $p)"
cd $p
echo $p
bash $p/setup_chemotion_db.sh