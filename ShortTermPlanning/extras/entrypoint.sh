#!/bin/sh

# Get the group ID of the Docker socket (if it exists)
if [ -e /var/run/docker.sock ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
    groupmod -g "$DOCKER_GID" docker
    newgrp docker
fi

mkdir -p /var/log/dynreact-logs/

# Give AppUser permissions to access the directory
chown -R appuser:appgroup /var/log/dynreact-logs
exec gosu appuser "$@" >> /proc/1/fd/1 2>> /proc/1/fd/2