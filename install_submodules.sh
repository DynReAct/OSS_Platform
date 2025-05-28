#!/usr/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $SCRIPT_DIR

# Get Poetry's env path for oss-plataform
if [[ -n "$VIRTUAL_ENV_PROMPT" && "$VIRTUAL_ENV_PROMPT" == *oss-plataform* ]] && [[ -n "$VIRTUAL_ENV" && "$VIRTUAL_ENV" == *oss-plataform* ]]; then
    POETRY_ENV_PATH=$(poetry env list --full-path | grep oss-plataform | grep Activated | awk '{print $1}')
    echo "Poetry environment 'oss-plataform' is already activated: ${POETRY_ENV_PATH:-$VIRTUAL_ENV}"
else
    echo "Activating Poetry environment 'oss-plataform'..."
    POETRY_ENV_PATH=$(poetry env list --full-path | grep oss-plataform | awk '{print $1}')
    if [[ -z "$POETRY_ENV_PATH" ]]; then
        echo "Error: No Poetry environment named 'oss-plataform' found."
        exit 1
    fi
    source "$POETRY_ENV_PATH/bin/activate"
    echo "Activated: $(which python)"
fi

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
cd ..

cat <<EOF > .env
# Environment Variables
CONFIG_PROVIDER=default+file:./data/config/site.json
COST_PROVIDER=ras:costs
PYTHONUNBUFFERED=1
SHORT_TERM_PLANNING_PARAMS=ras+file:./data/config/stp_context.json
SNAPSHOT_PROVIDER=ras+file:./data/snapshots
STP_FRONTEND=dynreact.stp_gui_ras.agentPageRas
EOF

poetry lock && poetry install --extras "ras"
cd $SCRIPT_DIR