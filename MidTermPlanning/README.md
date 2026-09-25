# DynReAct Lot creation

Source Code for Lot Creation procedure, using a Tabu search approach for the order to equipment allocation and a 
traveling salesman solver for the ordering of orders at a fixed equipment.

## Configuration

The lot creation algorithm has several configuration parameters, all of which can be set via environment variables.

```
# Setting TABU_NUM_CORES to 1 disables parallelism for the tabu search algorithm. By default, the value is set to min(8, cpu_count)-
TABU_NUM_CORES=1
# Define the virtual cost threshold for the creation of a new lot. Default value is 4.
TABU_MAX_TRANSITION_COST=10
# Set the timeout for the traveling salesman solver, determining the optimal order of orders in each iteration. Default value is 1.
TABU_ORTOOLS_TIMEOUT=2
# Configure a fixed random seed for the lot creation, leading to reproducible lot creation results, as long as no timeouts are hit. Recommended setting for tests. 
TABU_RAND_SEED=42
```

A comprehensive list of parameters can be found in the file 
[TabuParams.py](https://github.com/DynReAct/OSS_Platform/blob/main/MidTermPlanning/dynreact/lotcreation/TabuParams.py).

## Run tests

In the present folder run

```commandline
python -m unittest discover tests/unittests
```

In order to run an individual test case:

```commandline
 python ./tests/unittests/test_optimization.py OptimizationTest.test_lot_creation_with_predecessor
```

