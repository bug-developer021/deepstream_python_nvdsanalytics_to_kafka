#!/usr/bin/ bash


HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=localhost,127.0.0.1

DOCKERFILE=Dockerfile
# TAG=deepstream:6.1-triton-jupyter-python-custom
TAG=$1

docker build -f docker/$DOCKERFILE --network host   --build-arg HTTP_PROXY=$HTTP_PROXY --build-arg HTTPS_PROXY=$HTTPS_PROXY --build-arg NO_PROXY=$NO_PROXY -t $TAG .