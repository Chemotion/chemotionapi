#!/bin/bash

cd chem


jq -e '.dependencies["mini-css-extract-plugin"]' package.json >/dev/null
if [ $? -eq 0 ]; then
    echo "Dependency 'mini-css-extract-plugin' exists in dependencies"
else
    jq '.dependencies["mini-css-extract-plugin"] = "latest"' package.json > package.json.tmp \
  && mv package.json.tmp package.json
fi


