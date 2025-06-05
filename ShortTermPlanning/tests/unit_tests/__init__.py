import sys
from os.path import dirname, join, normpath

THIS_DIR = dirname(__file__)
PROJ_DIR = normpath(join(THIS_DIR, '..', '..', 'dynreact', 'shortterm'))
sys.path.append(PROJ_DIR)