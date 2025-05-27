#!/bin/bash

#######
# Basic Config
#######

sudo service socat-forwarding reload 
cd /workspace 
poetry init

cd DynReActBase
poetry lock && poetry install
cd ..

cd MidTermPlanning
poetry lock && poetry install
cd ..

cd SampleUseCase
poetry lock && poetry install
cd ..

cd ShortTermPlanning
poetry lock && poetry install --no-root
cd ..

cd DynReActService
poetry lock && poetry install

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

#######
# Config ZSH
#######
# powerline fonts for zsh theme
git clone https://github.com/powerline/fonts.git
cd fonts
./install.sh
cd .. && rm -rf fonts

# oh-my-zsh plugins
zsh -c 'git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/themes/powerlevel10k'
cp .devcontainer/extras/.zshrc ~
cp .devcontainer/extras/.p10k.zsh ~
