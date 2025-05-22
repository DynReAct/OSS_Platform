#!/usr/bin/bash

cd DynReActBase
poetry lock && poetry install
cd ..
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
cd MidTermPlanning
poetry lock && poetry install
cd ..
cd SampleUseCase
poetry lock && poetry install
cd ..
cd ShortTermPlanning
poetry lock && poetry install
cd ..
cd DynReActService
poetry lock && poetry install