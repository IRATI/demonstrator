# Building and Running the Docker Environment for the Demonstrator
[Docker](https://www.docker.com/) must be installed on the machine before anything can proceed.

In order to create the Demonstrator Docker environment make sure to be in the Docker folder and run the command

> make build

And let Docker do it's magic from there. Once the build is complete check that the Docker image is available with

> docker images

Should see an image called irati/demobase.

In order to run this image for the first time run the script in the tools folder

> ./dockerrun.sh

In order to enter this Docker container type

> docker exec -it irati-demo bash

You will be landed in to shell of the container and the main directory were the demonstrator will be run.
Follow the [README for the Demonstrator](https://github.com/IRATI/demonstrator/blob/master/README.md) to get things up and running.

In order to exit from the shell, CRTL-D.

In order to shutdown the running container use the command

> docker stop irati-demo

To start the container again just type

> docker start irati-demo
