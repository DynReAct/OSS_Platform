#!/bin/bash
# it is not so easy to exclude a directory (venv is large) with find -delete, so we simply go through the sub dirs explicitly
cd DynReActBase
find . -name '*.pyc' -delete
cd ../DynReActService
find . -name '*.pyc' -delete
cd ../MidTermPlanning
find . -name '*.pyc' -delete
cd ../SampleUseCase
find . -name '*.pyc' -delete
cd ../ShortTermPlanning
find . -name '*.pyc' -delete
