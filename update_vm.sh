#!/bin/bash

set -x

source gen.env

qemu-system-x86_64 "$vmimgpath" \
        --enable-kvm \
        -smp 2 \
        -m 1024M \
        -device e1000,netdev=mgmt \
        -netdev user,id=mgmt,hostfwd=tcp::2222-:22 \
        -vga std &
