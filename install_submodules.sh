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

cat <<EOF > .env
# Environment Variables
CONFIG_PROVIDER=default+file:./data/config/site.json
COST_PROVIDER=ras:costs
PYTHONUNBUFFERED=1
SHORT_TERM_PLANNING_PARAMS=ras+file:./data/config/stp_context.json
SNAPSHOT_PROVIDER=ras+file:./data/snapshots
STP_FRONTEND=dynreact.stp_gui_ras.agentPageRas
TOPIC_CALLBACK=Dyn-Callback
TOPIC_GEN=Dyn-Gen
EOF
