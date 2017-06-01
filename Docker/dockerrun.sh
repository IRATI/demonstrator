#!/bin/bash

# Give meaningful names
NAME=irati-demo

# Run the main asterisk container.
docker run \
    --privileged \
    --name $NAME \
    --net=host \
    -d -t irati/demobase
