# DynReAct sample plant performance model

DynReAct sample plant performance model

## Description

A plant performance model for DynReAct, for testing and development purposes.

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
# Set this property to introduce some randomness... otherwise the model always returns 1.
FEASIBILITY_RANDOM_THRESHOLD=0.5
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

See also the `ìf __name__ == "__main__"` run section of the file [PerformanceModelClient.py](../DynReActBase/dynreact/base/impl/PerformanceModelClient.py) for an example how to query the model.

## Integrate with sample use case

In order to activate the plant performance model for the sample use case, add the following line to the *.env* file in the folder *DynReActService*:

```commandline
PLANT_PERFORMANCE_MODEL_0="dynreact.base.impl.PerformanceModelClient:http://localhost:8081"
```

 