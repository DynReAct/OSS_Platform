# DynReAct Sample plant performance model

DynReAct Sample plant performance model

## Description

A plant performance model for DynReAct.

## Run

```commandline
python -m uvicorn dynreact.perfsample.service:app --reload --port 8051 --log-level debug
```

or create a corresponding run configuration in the IDE. The service description will then be available at http://localhost:8051/docs#/.

## Configuration

Create a file `.env` in the present directory with content

```
MODEL_ID=sample_model_1
MODEL_LABEL=My sample model
APPLICABLE_PROCESSES=FIN
```

This example applies to the finishing line, cf. process list in [site.json](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActService/data/site.json). For all configuration options, see [config.py](https://github.com/DynReAct/OSS_Platform/blob/main/SamplePerformanceModel/dynreact/perfsample/config.py)

## Test

In order to test this model from the Python console, navigate to the directory `DynReActService`, start a Python console, and execute

```python
from dynreact.base.impl.PerformanceModelClient import PerformanceModelClient, PerformanceModelClientConfig

c = PerformanceModelClient(PerformanceModelClientConfig(address="http://localhost:8051"))
c.id()
c.status()
```

