#!/bin/bash

apt-get update && apt-get install -y curl git git-lfs python3 gcc python3-dev python3-pip vim

# set the project name env variable
export KAL=/lustre/fsw/portfolios/nvr/users/pbelcak/keepalive

# cd into the project dir
cd $KAL

# get the python version
python3 --version
