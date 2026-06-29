"""Test support and regression coverage for OSS_Platform/ShortTermPlanning/tests/unit_tests/__init__.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

import sys
from os.path import dirname, join, normpath

THIS_DIR = dirname(__file__)
PROJ_DIR = normpath(join(THIS_DIR, '..', '..', 'dynreact', 'shortterm'))
sys.path.append(PROJ_DIR)