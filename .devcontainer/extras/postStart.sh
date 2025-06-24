#!/bin/zsh

WORKSPACE="/workspace"
git config --global --add safe.directory "$WORKSPACE"
sudo chown root:docker /var/run/docker.sock

LongTermPlanning="$WORKSPACE/DynReActService/LongTermPlanning"
if [ "$(ls -A $LongTermPlanning)" ]; then
    git config --global --add safe.directory "$LongTermPlanning"
fi

LotCreationRas="$WORKSPACE/DynReActService/LotCreationRas"
if [ "$(ls -A $LotCreationRas)" ]; then
    git config --global --add safe.directory "$LotCreationRas"
fi

ShortTermRAS="$WORKSPACE/DynReActService/ShortTermRAS"
if [ "$(ls -A $ShortTermRAS)" ]; then
    git config --global --add safe.directory "$ShortTermRAS"
fi
