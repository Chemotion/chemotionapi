#!/bin/bash

echo "Make sure docker and curl is installed"
# Prompt the user for each environment variable, with default values

curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/.env.example
mv .env.example .env

read -p "Enter public URL [http://0.0.0.0:4000/]: " PUBLIC_URL
PUBLIC_URL=${PUBLIC_URL:-http://0.0.0.0:4000/}

sed -i "s/^USERNAME=.*/USERNAME=$new_username/" .env

read -p "Enter open docker-compose prot [4000]: " PROJECT_WEB_PORT
PROJECT_WEB_PORT=${PROJECT_WEB_PORT:-4000}

read -p "Enter UPDATE_INTERVAL [600]: " UPDATE_INTERVAL
UPDATE_INTERVAL=${UPDATE_INTERVAL:-600}

sed -i "s/^UPDATE_INTERVAL=.*/UPDATE_INTERVAL=$UPDATE_INTERVAL/" .env
sed -i "s/^PUBLIC_URL=.*/PUBLIC_URL=$PUBLIC_URL/" .env
sed -i "s/^PROJECT_WEB_PORT=.*/PROJECT_WEB_PORT=$PROJECT_WEB_PORT/" .env

echo ".env file created with the following content:"

echo "create shared folder"

mkdir shared
mkdir shared/backup
mkdir shared/pullin
mkdir shared/pullin/config
mkdir shared/restore
mkdir shared/shell_scripts

echo "Downloading missing files!"

curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/docker-compose.yml
cd shared/shell_scripts
curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/shared/shell_scripts/example.sh
curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/shared/shell_scripts/update_npm.sh
cd ../pullin/config
curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/shared/pullin/config/database.yml
cd ../../restore
curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/shared/restore/example.sql
cd ..

curl -O https://raw.githubusercontent.com/StarmanMartin/ChemotionTestDeployment/main/shared/BRANCH.txt
