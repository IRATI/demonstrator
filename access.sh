#!/bin/sh

source ./gen.env

MACHINE_ID=${1:-1}
SSH_PORT=$(( MACHINE_ID + baseport))

echo "Accessing buildroot VM #${MACHINE_ID}"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentityFile=buildroot/irati_rsa -p ${SSH_PORT} root@localhost
