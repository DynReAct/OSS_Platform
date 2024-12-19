# DynReActBase

Experimental DynReActBase package.

## Python 

### Install

Tested with Python 3.12, but targeting at least 3.11 and 3.12. It is recommended to setup a virtual environment for the project:

```commandline
python -m venv --upgrade-deps venv
```

Activate this environment, e.g. via the IDE, or on Windows in the Anaconda Prompt: `.\venv\Scripts\activate.bat`.

Use the requirements.txt file in the base directory to install the required dependencies:

```commandline
pip install -r requirements.txt
```

or

```commandline
python -m pip install -r requirements.txt
```

### Build wheel

```
pip wheel . --no-cache-dir --disable-pip-version-check --no-deps --wheel-dir dist
```

For offline operation installation of the following packages is required:

```
setuptools>=70, <71
wheel==0.43.0
```

In addition, the `--no-build-isolation` parameter must be specified:

```
pip wheel . --no-index --disable-pip-version-check --no-deps --wheel-dir dist --no-build-isolation
```

## Docker

To build in Docker, run 

```commandline
./build.sh
```

## Model
