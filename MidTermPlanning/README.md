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

## Results

By default, results of the mid-term planning optimization are stored in the folder *DynReActService/results/lotcreation*, and are organized in subfolders by 
snapshot date. Below the snapshots there are additional subfolders per process stage. For instance, the resulting folder structure may look as follows:

```
| results
|  - lotcreation
|     - 1738364400000
|        - PKL
|        - CRL
|     - 1738368000000
|        - PKL
```

By deleting the *lotcreation* folder all existing MTP results can be removed. The base folder can be configured by means of the `RESULTS_PERSISTENCE`
environment variable. To change to a different directory, set

```
RESULTS_PERSISTENCE=default+file:./path/to/folder
```

It is also possible to implement a custom [ResultsPersistence](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActBase/dynreact/base/ResultsPersistence.py) provider, 
to store results in a database, for instance. 

## Run tests

In the present folder run

```commandline
python -m unittest discover tests/unittests
```

In order to run an individual test case:

```commandline
 python ./tests/unittests/test_optimization.py OptimizationTest.test_lot_creation_with_predecessor
```

