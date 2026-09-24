# Customizing DynReAct

## Content

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
snapshot provider, such as `mycompany+mes:db-address:1027`, and the basic [`Site`](#site-configuration) object.

In order to activate the custom snapshot provider, the environment parameter `SNAPSHOT_PROVIDER` must be set:

```
SNAPSHOT_PROVIDER=mycompany+mes:db-address:1027
```

In general, it is assumed that the snapshot provider resides within the module `dynreact.snapshot.<PROFILE_ID>`. 
Otherwise, the module can be prepended as follows:

```
SNAPSHOT_PROVIDER=class:custom.module.path.MySnapshotProvider,mycompany+mes:db-address:1027
```

### Further sources

Besides the snapshot provider, some other data sources can be provided:

* [ShiftsProvider](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/shifts_provider.html): mainly used by 
   the long-term planning but also the mid-term planning (TODO explain)  
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

in our example. It is assumed here that the custom `LotSink` subclass resides in the module `dynreact.lotsink.<PROFILE_ID>`.
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

## Optimizations

It is possible to adapt the configuration of the existing optimization algorithms, and even to replace them with
custom implementations. This is not necessary nor recommended for the initial tests of the DynReAct system, however.

### Long-term planning

#### LTP configuration

#### LTP algorithm

The long-term planning algorithm can be exchanged by means of the environment variable `LONG_TERM_PLANNING`. Example:

```
LONG_TERM_PLANNING=class:path.to.custom.ltp.LongTermPlanning:mycompany:./algoSettings.json
```

The configured class must implement the [LongTermPlanning](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/longtermplanning.html)
interface.

The default implementation uses the Picos modeling language to formulate the LTP as a convex optimization problem
and the Ecos solver for the solution. It can be found in the [LongTermPlanning](https://github.com/DynReAct/OSS_Platform/tree/main/LongTermPlanning)
subproject, with the interface implementation residing in the file [LongTermPlanningImpl.py](https://github.com/DynReAct/OSS_Platform/blob/main/LongTermPlanning/dynreact/ltp/LongTermPlanningImpl.py).

### Mid-term planning

#### Lot creation configuration

#### Batch lot creation

#### Lot creation algorithm

The lot creation algorithm can be exchanged by means of the environment variable `LOT_CREATION`. Example:

```
LOT_CREATION=class:path.to.custom.lotcreation.LotCreation:mycompany:./algoSettings.json
```

The configured class must implement the [LotsOptimizationAlgo](https://dynreact.github.io/OSS_Platform/docs/DynReActBase/lots_optimizer.html#lotsoptimizationalgo-class)
interface.

The existing implementation is based on a TabuSearch approach for the allocation of orders to equipments, with a traveling salesman
solver determining the optimal order of orders. It can be found in the
[MidTermPlanning](https://github.com/DynReAct/OSS_Platform/tree/main/MidTermPlanning) subproject,
with the interface implementation residing in the file [LotsOptimizerImpl.py](https://github.com/DynReAct/OSS_Platform/blob/main/MidTermPlanning/dynreact/lotcreation/LotsOptimizerImpl.py).

### Short-term planning




