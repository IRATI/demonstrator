#!/bin/bash

if [ -n "$1" ]; then
    X="${1}."
else
    X=""
fi

./configure /home/vmaffione/irati/local /home/vmaffione/git/vm/${X}irati.qcow2
./gen.py
