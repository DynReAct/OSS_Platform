# DynReAct Sample plant performance model

DynReAct Sample plant performance model

## Description

A plant performance model for DynReAct.

## Run

```commandline
python -m uvicorn dynreact.perfsample.service:app --reload --port 8051 --log-level debug
```

or create a corresponding run configuration in the IDE. The service description will then be available at http://localhost:8051/docs#/.


