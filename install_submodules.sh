#!/usr/bin/bash

git submodule update --init --recursive
cd DynReActService

cd ShortTermRAS
poetry lock && poetry install
cd ..

cd LotCreationRas
poetry lock && poetry install
cd ..

cd LongTermPlanning
poetry lock && poetry install
cd ../..