# LotCreation

Source Code for Lot Creation procedure using tabu search approach

## Python 

Tested with Python 3.12, but targeting at least 3.11 and 3.12. It is recommended to setup a virtual environment for the project:

```commandline
python -m venv --upgrade-deps venv
```

Activate this environment, e.g. via the IDE, or on Windows in the Anaconda Prompt: `.\venv\Scripts\activate.bat`.

Use the requirements.txt file in the base directory to install the required dependencies (assuming the *DynReActBase* module has been built before):

```commandline
pip install -r requirements.txt -r requirements_local.txt
```

or

```commandline
python -m pip install -r requirements.txt -r requirements_local.txt
```
## Build wheel

```
pip wheel . --no-cache-dir --disable-pip-version-check --no-deps --wheel-dir dist
```

## Run tests

In the present folder run

```commandline
python -m unittest discover tests/unittests
```

In order to run an individual test case:

```commandline
 python ./tests/unittests/test_optimization.py OptimizationTest.test_lot_creation_with_predecessor
```

