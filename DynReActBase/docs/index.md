# Dynreact Base

Dynreact basic components and interfaces:

- `model.py`: contains the basic domain model for the DynReAct production planning software
- `SnapshotProvider.py`: defines the SnapshotProvider data source interface
- `SnapshotImporter.py`: defines the SnapshotImporter extension of SnapshotProvider
- `ShiftsProvider.py`: defines the ShiftsProvider data source interface
- `ProductionHistoryReader.py`: defines the ProductionHistoryReader data source interface
- `LotSink.py`: defines the LotSink data sink interface
- `CostProvider.py`: contains all the custom logic and classes for building an objective function for schedules
- `LongTermPlanning.py`: provides the interface for the LongTermPlanning algorithm
- `LotsOptimizer.py`: contains the interface specification for the mid-term planning algorithm
- `PlantPerformanceModel.py`: defines the PlantPerformanceModel interface
