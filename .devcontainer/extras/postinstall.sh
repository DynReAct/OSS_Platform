#!/bin/bash

#######
# Basic Config
#######

sudo service socat-forwarding reload 
cd /workspace 
poetry init

cd ShortTermPlanning
poetry lock && poetry install --no-root
cd ..

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
