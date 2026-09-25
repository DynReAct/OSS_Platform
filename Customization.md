# Customizing DynReAct

## Content

* [Overview](#overview)
* [Site configuration](#site-configuration)
* [Data sources and sinks](#data-sources-and-sinks)
  * [Custom profiles](#custom-profiles) 
  * [Snapshot generation](#snapshot-generation)
  * [Further sources](#further-sources)
  * [Lot sinks](#lot-sinks)
* [Cost functions](#cost-functions)
* [Optimizations](#optimizations)
  * [Long-term planning](#long-term-planning)
    * [LTP configuration](#ltp-configuration)
    * [LTP algorithm](#ltp-algorithm)
  * [Mid-term planning](#mid-term-planning)
    * [Lot creation configuration](#lot-creation-configuration)
    * [Batch lot creation](#batch-lot-creation)
    * [Lot creation algorithm](#lot-creation-algorithm)
  * [Short-term planning](#short-term-planning)

## Overview

Configuring DynReAct for a new planning/scheduling use case requires some configuration, the provision of data sources and sinks, 
and of virtual costs for production sequences. 
SWhich data sources are required exactly depends on the selection of DynReAct components to be used. 
Whereas the long-term planning models the flow of material through the whole site, keeping buffer levels within the defined boundaries
and ensuring sufficient supply for each equipment unit, the mid-term and short-term planning modules generate sequences of
production orders and therefore have similar data requirements. The three modules can be used in conjunction, but all of them
can be adopted as standalone solutions, allowing for a phased introduction.

Documentation of DynReAct Python interfaces can be found under the following link: [https://dynreact.github.io/OSS_Platform/docs/](https://dynreact.github.io/OSS_Platform/docs/), and
the DynReAct REST interface is documented at [https://dynreact.github.io/OSS_Platform/docs/service/index.html](https://dynreact.github.io/OSS_Platform/docs/service/index.html).
Source code for the basic models, such as `Order`, `Snapshot` and `Lot` can be found in [model.py](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActBase/dynreact/base/model.py),
and all interfaces are defined in the [`dynreact.base`](https://github.com/DynReAct/OSS_Platform/tree/main/DynReActBase/dynreact/base) module. 

The REST service is based on the *FastAPI* framework, it can be found in [service.py](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActService/dynreact/service/service.py), 
and the web frontend is based on Plotly's *Dash*.     

## Site configuration

The site configuration provides the basic entities a production site consists of:

* [Processes](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#process-class): DynReAct assumes a flexible flow shop scheduling problem, 
    where each site consists of a series of a process steps, with a fixed set of equipment associated to it.    
* [Equipment](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#equipment-class): Every equipment unit is associated to exactly one process step.
    capacity and potentially restrictions regarding the material classes that can be processed. Each equipment unit should be connected to a storage unit for incoming and outgoing material.
* [Storages](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#storage-class): Storages provide buffers between the equipment units. 
    They are only relevant for the long-term planning.
* [Material categories](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#materialcategory-class) and
    [classes](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#materialclass-class): these can be used to provide a rough categorization of the different product types. 
    They should be used when there are constraints on equipment or storages, for instance, when certain units cannot process all types of products. 

All of these entities and the [Site](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#site-class) class are defined in the 
[model.py](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActBase/dynreact/base/model.py) source file. An example for 
a *site.json* file can be found in [repository](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActService/data/site.json).

## Data sources and sinks

### Custom profiles

The recommended way to announce the existence of custom Python modules implementing some of the DynReAct 
data source and sink interfaces is the activation of a named profile. 
Named profiles are a means to configure DynReAct to look for certain services in standardised locations. 
A profile `mycompany` is activated by means of the environment variable:

```
DYNREACT_PROFILE=mycompany
```

### Snapshot generation

A production [Snapshot](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#snapshot-class) provides information about the 
production orders currently being processed or waiting to be processed in the site,
along with planned order sequences ([*Lots*](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#lot-class)) for each equipment unit. This is the minimum required data source for the mid-term
and short-term planning modules. For this purpose, a [SnapshotProvider](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/snapshot_provider.html) 
class must be defined in the custom Python project. Its `__init__` method takes two arguments, a URL identifying the
snapshot provider, such as `mycompany+mes:db-address:1027`, and the basic [`Site`](#site-configuration) object. There is a 
set of predefined properties every [Order](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#order-class) should possess.
Additionally, custom properties can be added in the [`material_properties`](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/model.html#dynreact.base.model.Order.material_properties) 
field, which holds an object of a generic subtype of the Pydantic [`BaseModel`](https://pydantic.dev/docs/validation/dev/api/pydantic/base_model/) class. 
Define your custom subtype as in the following example:

```python
from pydantic import BaseModel

class MyOrderProperties(BaseModel, use_attribute_docstrings=True):
    """
    This class contains custom order properties
    """
    
    target_width: float
    "Width in mm"
    target_height: float
    "Height in mm"
    ...
```

Then ensure that the SnapshotProvider generates orders of generic type `Order[MyOrderProperties]`, i.e., whose `material_properties`
field is an instance of the class `MyOrderProperties`.

In order to activate the custom snapshot provider, the environment parameter `SNAPSHOT_PROVIDER` must be set:

```
SNAPSHOT_PROVIDER=mycompany+mes:db-address:1027
```

In general, it is assumed that the snapshot provider resides within the module `dynreact.snapshot.<PROFILE_ID>`. 
Otherwise, the module can be prepended as follows:

```
SNAPSHOT_PROVIDER=class:custom.module.path.MySnapshotProvider,mycompany+mes:db-address:1027
```

An example of a SnapshotProvider is included in DynReAct core: 
[FileSnapshotProvider](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActBase/dynreact/base/impl/FileSnapshotProvider.py).
It reads snapshots from .csv files, where every row corresponds to a material unit, and one or multiple units make up an
order. It supports custom order properties in columns whose name begins with `material_`.  

### Further sources

Besides the snapshot provider, some other data sources can be provided:

* [ShiftsProvider](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/shifts_provider.html): mainly used by 
   the long-term planning but also the mid-term planning (TODO to be extended).  
* [ProductionHistoryReader](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/prod_history_reader.html): only relevant
   for the long-term planning. Is used for comparing the actual production with the long-term targets, and thus creating updates of the latter.  

### Lot sinks

A [LotSink](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/lot_sink.html) is responsible for transferring lots generated by the 
DynReAct mid-term module to the backend (such as the MES, or production planning system - PPS). The lot transfer always has to be initiated by a user,
automatic lot transfer is not currently foreseen.

The `__init__` function of a lot sink takes three arguments, a URL identifying 
the source and possibly some required arguments (example: `mycompany+mes:db-address:1027`), the basic [`Site`](#site-configuration) object,
and a permission manager, which can be used to validate the user's permission to transfer lots.

In order to activate the configured LotSink, the environment parameter `LOT_SINK` must be set:

```
LOT_SINK=mycompany+mes:db-address:1027
```

in our example. Multiple sinks can be separated by a semi-colon ";". It is assumed here that the custom `LotSink` subclass resides in the module `dynreact.lotsink.<PROFILE_ID>`.
Otherwise, the class module can be prepended, as follows:

```
LOT_SINK=class:custom.module.path.MyLotSink,mycompany+mes:db-address:1027
```

For testing purposes, a file-storage based lot sink is included in the open-source package. It can be enabled by means of the configuration

```
LOT_SINKS=default+file:./testlots
```

Where *./testlots* is the folder to store lots in.

## Cost functions

Another core component of DynReAct is the virtual costs function, or objective function. It defines primarily the transition costs between orders
at a given equipment unit. The interface is called [CostProvider](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/cost_provider.html), 
and the central method that needs to be implemented is 
[`transition_costs`](https://github.com/DynReAct/OSS_Platform/blob/4d5297bb500f9c3b68e4cb1b0f7a7745b70a790f/DynReActBase/dynreact/base/CostProvider.py#L26-L42):  

```python
from dynreact.base.model import Equipment, Order, Material

def transition_costs(self, plant: Equipment, current: Order, next: Order, current_material: Material | None = None, next_material: Material | None = None) -> float:
        """
        Calculates the transition costs for two orders at a given plant. If materials are specified,
        then the transition costs between individual materials are evaluated instead.
        This function does not take into account global constraints and objectives.

        Parameters:
            plant: equipment
            current: order 1
            next: order 2
            current_material: optional material unit belonging to order 1
            next_material: optional material unit belonging to order 2

        Returns:
            the virtual transition costs associated to the order-to-order transition
        """
        pass
```

It assigns virtual costs to the transition from the order named `current` to the order `next`. Optionally, it is possible 
to consider also the material units (an order may consist of one or more material units to be processed). However, support
for material-level transitions is currently limited, therefore the cost provider should be able to deal with `None` values
for those materials.

Returned cost values should never be negative, but they may be zero if the transition does not involve any setup activities
and is not constrained in any other way at the equipment. The more setup activities or waiting times are required between orders,
the higher the costs should be. In the default setup, a cost value 4 defines the threshold for the creation of a new lot. 
I.e., orders with transition costs <= 4 may succeed one another in a single lot, whereas the DynReAct lot creation algorithm
will create a new lot whenever it determines that the optimal order sequence has two subsequent orders with transition costs > 4.
This threshold can be configured, however, see section [Lot creation configuration](#lot-creation-configuration) below.

Besides `transition_costs()`, the method `update_transition_costs()` must be implemented, as well as `objective_function()`.
TODO explain...

An example of a CostProvider can be found in the DynReAct SampleUseCase module: 
[CostCalculatorImpl](https://github.com/DynReAct/OSS_Platform/blob/main/SampleUseCase/dynreact/cost/CostCalculatorImpl.py).
It is based on a custom order properties class [`SampleMaterial`](https://github.com/DynReAct/OSS_Platform/blob/main/SampleUseCase/dynreact/sample/model.py#L6),
as explained in the section on the [snapshot provider](#snapshot-generation). The entries of the `SampleMaterial` instances
are filled from the snapshot columns whose names start with `material_`, cf. the [sample snapshot](https://github.com/DynReAct/OSS_Platform/blob/main/DynReActService/data/snapshots/snapshot_2024-12-31T00_00.csv).

The custom `CostProvider` should reside in the module `dynreact.cost.<PROFILE_ID>`, in which case it will be activated automatically. 
Alternatively, it is possible to specify the cost provider using an environment variable:

```
COST_PROVIDER=class:dynreact.custom.path.CostProvider,mycompany+mes:db-address:1027
```

Its `__init__` method should accept two arguments, a URL (which may be `None`, unless specified via an env var as in the example above),
and the `Site` object. 

## Optimizations

It is possible to adapt the configuration of the existing optimization algorithms, and even to replace them with
custom implementations. This is not necessary nor recommended for the initial tests of the DynReAct system, however.

### Long-term planning

The long-term planning algorithm uses the Picos modeling language to formulate the LTP as a convex optimization problem
and the Ecos solver for the solution. It can be found in the [LongTermPlanning](https://github.com/DynReAct/OSS_Platform/tree/main/LongTermPlanning)
subproject, with the interface implementation residing in the file [LongTermPlanningImpl.py](https://github.com/DynReAct/OSS_Platform/blob/main/LongTermPlanning/dynreact/ltp/LongTermPlanningImpl.py).

#### LTP configuration

The long-term planning algorithm has several configuration parameters, all of which can be set via environment variables.

```
# Maximum number of iterations for the Picos solver. See https://picos-api.gitlab.io/picos/api/picos.modeling.options.html#option-max-iterations. Default is 250.
LTP_ITERATIONS=100
# The optimization tries to keep storage levels close to 50%. This factor can be used to adapt the weight of this target in the objective function. Default value: 1.
LTP_WEIGHT_STORAGE_LEVEL=2
# The optimization aims for the total production per material class to arrive at the predefined target values. This factor can be used to adapt the weight of this target in the objective function. Default: 1.
LTP_WEIGHT_CLASS_TARGETS=2
# The optimization tries to arrive at an even distribution of material classes in all buffers at the end of the considered period. This factor can be used to adapt the weight of this target in the objective function. Default: 1.
LTP_WEIGHT_STORAGE_LEVEL_MAT_FINAL=2
# Weight factor for the initial storage level of input buffers (feeding equipment in the first process step) in the objective function. Default value: 1.
LTP_WEIGHT_STORAGE_LEVEL_INPUT=2
# Enable some debugging checks and messages
LTP_DEBUG=true
```

These parameters are defined in the source file [LtpParams.py](https://github.com/DynReAct/OSS_Platform/blob/main/LongTermPlanning/dynreact/ltp/LtpParams.py)

#### LTP algorithm

The long-term planning algorithm can be exchanged by means of the environment variable `LONG_TERM_PLANNING`. Example:

```
LONG_TERM_PLANNING=class:path.to.custom.ltp.LongTermPlanning:mycompany:./algoSettings.json
```

The configured class must implement the [LongTermPlanning](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/longtermplanning.html)
interface.

### Mid-term planning

The mid-term planning or lot creation algorithm is based on a TabuSearch approach for the allocation of orders to equipments, with a traveling salesman
solver determining the optimal order of orders. It can be found in the
[MidTermPlanning](https://github.com/DynReAct/OSS_Platform/tree/main/MidTermPlanning) subproject,
with the interface implementation residing in the file [LotsOptimizerImpl.py](https://github.com/DynReAct/OSS_Platform/blob/main/MidTermPlanning/dynreact/lotcreation/LotsOptimizerImpl.py).

#### Lot creation configuration

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

#### Batch lot creation

It is possible to run the lot creation periodically in the background, setting the env var `LOTS_BATCH_CONFIG`. Example:  

```
LOTS_BATCH_CONFIG=19:00;P1D;PKL:1000:PT15M,CRL:500:PT30M 
```

to run daily at 19:00 (local server time), for the two process stages with ids *PKL* and *CRL*, allowing for 1000 iterations and 15 minutes execution time, 
respectively 750 iterations and 30 minutes duration.

#### Lot creation algorithm

The lot creation algorithm can be exchanged by means of the environment variable `LOT_CREATION`. Example:

```
LOT_CREATION=class:path.to.custom.lotcreation.LotCreation:mycompany:./algoSettings.json
```

The configured class must implement the [LotsOptimizationAlgo](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/lots_optimizer.html#lotsoptimizationalgo-class)
interface.


### Short-term planning




