#!/bin/bash

#######
# Basic Config
#######

sudo service socat-forwarding reload 
cd /workspace

#######
# Poetry
#######

poetry init --no-interaction --name OSS_Plataform --python "^3.12"
poetry install --no-root
eval $(poetry env activate)

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
poetry lock && poetry install
cd ..

cd DynReActService
poetry lock && poetry install
cd /workspace

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
