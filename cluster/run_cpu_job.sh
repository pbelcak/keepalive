#!/bin/sh
JOB_NAME="$1"

# Store the arguments in a variable
args=""
# Iterate over each argument
for arg in "$@"; do
  # Append the argument to the args variable with a space
  args="$args $arg"
done

PROJECT_PATH=$KAL
CODE_PATH=${PROJECT_PATH}

submit_job --gpu 0 --nodes 1 --partition=cpu --duration 24 -n "$1" --image nvcr.io/nvidia/base/ubuntu:22.04_20240212 --command 'source '"$KAL"'/cluster/prepare_cpu_job.sh; source '"$KAL"'/cluster/secrets.sh; PYTHONPATH='"$CODE_PATH"':'"$PROJECT_PATH"':${PYTHONPATH} python3 '"$KAL"'/day_sleeper.py '"$args"' '