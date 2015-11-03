#!/bin/bash

if [ -n "$1" ]; then
    PORT="${1}"
    shift
else
    PORT="2222"
fi

if [ -n "$1" ]; then
    X="${1}."
    shift
else
    X=""
fi

./configure /home/vmaffione/irati/local /home/vmaffione/git/vm/${X}irati.qcow2
./gen.py -p $PORT
