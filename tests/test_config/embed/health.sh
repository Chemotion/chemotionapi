#!/bin/bash

if [[ "${CONFIG_ROLE}" == "eln" || "${CONFIG_ROLE}" == "combine" ]]; then
    exec curl --fail "http://localhost:4000/about"
elif [[ "${CONFIG_ROLE}" == "worker" ]]; then
    exec pgrep -ia bundle
else
    echo "ERROR: Please specify CONFIG_ROLE ('eln'/'worker'/'combine')."
    exit 1
fi