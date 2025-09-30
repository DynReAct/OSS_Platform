#!/bin/bash
MSYS_NO_PATHCONV=1 docker build -f Dockerfile_service -t dynreact.eu/oss/dynreact-service .

