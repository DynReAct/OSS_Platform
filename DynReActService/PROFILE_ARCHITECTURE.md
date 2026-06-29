# DynReAct Profile Architecture

## Overview

DynReAct uses profile-based dependency injection to load domain-specific implementations such as `ras`, `oss`, or custom extensions without coupling them directly to the core service code.

The current model is based on:

- `plugins.py` as the service-facing entry point
- `module_loader.py` as the shared module/class resolver
- `state.py` using the same profile-aware loading flow for short-term planning

`container.py` is no longer the active loading path in the `profiles` branch.

## Loading Flow

```text
1. DynReActSrvConfig reads the active profile
2. Plugins receives the config
3. Plugins selects the target module path
4. module_loader resolves and instantiates an explicit subclass
5. The resulting provider is cached by Plugins/state
```

## Resolution Rules

### 1. Explicit class override

If a service config uses an explicit class reference such as:

```text
class:dynreact.custom.MySnapshotProvider,customs+file:./snapshot.csv
```

DynReAct:

1. resolves `dynreact.custom.MySnapshotProvider`
2. verifies that it is a subclass of the expected interface
3. instantiates it with the remaining provider URL

This path has priority over profile loading and is the preferred way to override a single service while keeping a profile active.

### 2. Profile module resolution

If a profile is configured, DynReAct tries modules like:

- `dynreact.snapshot.ras`
- `dynreact.config.ras`
- `dynreact.shortterm.ras`
- `dynreact.shifts.ras`

The loader searches the module for an explicit subclass of the expected interface. It does not require an `Impl` suffix.

### 3. Default fallback

For services with a known built-in default implementation, DynReAct falls back to the base implementation when appropriate, for example:

- `FileSnapshotProvider`
- `FileConfigProvider`
- `FileDowntimeProvider`
- `FileResultsPersistence`
- `FileAvailabilityPersistence`
- `FileAggregationPersistence`
- `FileLotSink`
- `DummyShiftsProvider`
- `SimpleLongTermPlanning`

## Important Design Choice

DynReAct now uses explicit classes only for provider discovery.

Legacy factory functions such as `create()` and `create_provider()` are no longer part of the active loading contract. This improves:

- subtype validation before instantiation
- readability of profile modules
- maintainability of the shared loader
- predictability during CI/CD verification

## Directory Pattern For A Profile

Example layout for a `ras` profile:

```text
ShortTermRAS/
├── dynreact/
│   ├── config/
│   │   └── ras.py
│   ├── snapshot/
│   │   └── ras.py
│   ├── shifts/
│   │   └── ras.py
│   └── shortterm/
│       └── ras.py
```

Each profile module should expose a concrete class compatible with the corresponding DynReAct interface.

## Implementation Example

```python
from dynreact.base.SnapshotProvider import SnapshotProvider


class RasSnapshotProvider(SnapshotProvider):
    def __init__(self, provider_url: str, site):
        self._provider_url = provider_url
        self._site = site
```

This class can live in `dynreact.snapshot.ras` directly, or be imported there from another file.

## What Is No Longer Required

- a class name ending in `Impl`
- a `create()` factory function
- a `create_provider()` factory function
- wiring through `container.py`

## Debugging

### Check which class was loaded

```python
from dynreact.plugins import Plugins
from dynreact.app_config import DynReActSrvConfig

plugins = Plugins(DynReActSrvConfig(profile="ras"))
provider = plugins.get_snapshot_provider()
print(type(provider).__module__, type(provider).__name__)
```

### Common failure modes

| Issue | Likely cause | Suggested fix |
|---|---|---|
| `Module ... not found` | The profile module does not exist | Add the corresponding `dynreact.<service>.<profile>` module |
| `Failed to load module ... of type ...` | No compatible subclass is exposed | Export a class that subclasses the expected interface |
| Explicit `class:` override fails | Wrong module path or class name | Verify the full `module.ClassName` reference |

## CI/CD Note

The local verification harness in `verification_local/` has been aligned with the current profile architecture and validated against short-term planning scenarios `00` through `08`.

## References

- [module_loader.py](/home/jordieres/soft/RAS_main/OSS_Platform/DynReActService/dynreact/module_loader.py)
- [plugins.py](/home/jordieres/soft/RAS_main/OSS_Platform/DynReActService/dynreact/plugins.py)
- [state.py](/home/jordieres/soft/RAS_main/OSS_Platform/DynReActService/dynreact/state.py)
