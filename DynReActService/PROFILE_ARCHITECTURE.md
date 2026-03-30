# Arquitectura de Plugins DynReAct - Dependency Injection

## Descripción General

La arquitectura de DI implementada permite cargar diferentes implementaciones de componentes (Snapshot, Config, Performance, etc.) basados en **profiles** (oss, ras, custom, etc.) sin acoplar el código específico de cada dominio al código OSS base.

## Flujo de Carga

```
1. DynReActSrvConfig (carga profile)
   ↓
2. Plugins inicia con config
   ↓
3. Plugins crea Container con profile
   ↓
4. Container.get_snapshot_provider()
   → Intenta cargar: dynreact.snapshot.{profile}
   → Compatibilidad transitoria: {profile}.dynreact.snapshot
   → Fallback a: dynreact.snapshot (si profile falla)
   ↓
5. Retorna implementación RAS/OSS/Custom
```

## Configuración

### Opción 1: Variable de Entorno

```bash
export PROFILE=ras
python -m uvicorn run:fastapi_app --host 192.168.110.68 --reload --log-level debug
```

### Opción 2: Archivo `.env`

```env
PROFILE=ras
SNAPSHOT_PROVIDER=ras+file:../../data/snapshots
CONFIG_PROVIDER=ras+file:../../data/config/site.json
SHORT_TERM_PLANNING_PARAMS=ras+file:../../data/config/stp_context.json
```

### Opción 3: Parámetro en código

```python
from dynreact.app_config import DynReActSrvConfig

config = DynReActSrvConfig(
    profile="ras",
    snapshot_provider="ras+file:../../data/snapshots"
)
```

## Estructura de Directorios

Para agregar un nuevo profile (ej: "ras"):

```
ShortTermRAS/
├── pyproject.toml
├── dynreact/
│   ├── snapshot/
│   │   ├── __init__.py
│   │   └── SnapshotProviderImpl.py      # RasSnapshotProviderImpl
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── ConfigurationProviderImpl.py # RasConfigurationProviderImpl
│   │
│   ├── performance/
│   │   ├── __init__.py
│   │   └── PerformanceModelImpl.py      # RasPerformanceModelImpl
│   │
│   └── energy_kpi/
│       ├── __init__.py
│       └── EnergyKpiImpl.py             # RasEnergyKpiImpl
```

## Cómo Funciona el Container

El `Container` en `OSS_Platform/DynReActService/dynreact/container.py`:

1. **Recibe profile** (ej: "ras") de config
2. **Intenta cargar módulos dinámicamente**:
   - Primero: `dynreact.{component}.{profile}`
   - Compatibilidad transitoria: `{profile}.dynreact.{component}`
   - Luego: `dynreact.{component}` (fallback OSS)
3. **Busca implementación en el módulo**:
   - Clases terminadas en `Impl` (ej: `RasSnapshotProviderImpl`)
   - Funciones `create()` o `create_provider()`
4. **Instancia y cachea** el resultado

## Implementación de Componentes RAS

### 1. SnapshotProviderImpl

```python
# ShortTermRAS/dynreact/snapshot/SnapshotProviderImpl.py

from dynreact.base.impl.FileSnapshotProvider import FileSnapshotProvider

class RasSnapshotProviderImpl(FileSnapshotProvider):
    def __init__(self, provider_url: str, site: Site):
        super().__init__(provider_url, site)
        # Agregar lógica RAS-específica
```

**Requisitos:**
- Nombre de clase debe terminar en `Impl`
- Constructor recibe: `(provider_url: str, site: Site)`
- Debe extender o implementar `SnapshotProvider` interface

### 2. ConfigurationProviderImpl

```python
# ShortTermRAS/dynreact/config/ConfigurationProviderImpl.py

from dynreact.base.impl.FileConfigProvider import FileConfigProvider

class RasConfigurationProviderImpl(FileConfigProvider):
    def __init__(self, config_url: str):
        super().__init__(config_url)
```

### 3. PerformanceModelImpl

```python
# ShortTermRAS/dynreact/performance/PerformanceModelImpl.py

from dynreact.base.PlantPerformanceModel import PlantPerformanceModel

class RasPerformanceModelImpl(PlantPerformanceModel):
    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site
```

### 4. Energy KPI Provider

```python
# ShortTermRAS/dynreact/energy_kpi/EnergyKpiImpl.py

class RasEnergyKpiImpl:
    def __init__(self, site=None):
        self._site = site
```

## Agregar Nuevos Componentes

### Paso 1: Crear directorio en ShortTermRAS

```bash
mkdir -p ShortTermRAS/dynreact/<component_name>
```

### Paso 2: Crear `__init__.py`

```python
# ShortTermRAS/dynreact/<component_name>/__init__.py

from .ComponentImpl import RasComponentImpl

__all__ = ["RasComponentImpl"]
```

### Paso 3: Crear implementación

```python
# ShortTermRAS/dynreact/<component_name>/ComponentImpl.py

class RasComponentImpl:
    def __init__(self, *args, **kwargs):
        pass
```

### Paso 4: Agregar al Container (si es necesario)

```python
# OSS_Platform/DynReActService/dynreact/container.py

def get_<component_name>(self, *args):
    if '<component_name>' not in self._cache:
        module = self._load_profile_module('<component_name>')
        self._cache['<component_name>'] = self._create_provider(module, *args)
    return self._cache.get('<component_name>')
```

## Debugging

### Ver qué profile está activo

```python
# En tu código
from dynreact.app import config
print(f"Profile: {config.profile}")
```

### Erro común: "Could not load snapshot for profile 'ras'"

**Causas:**
1. Módulo `ShortTermRAS.dynreact.snapshot` no existe
2. Clase no termina en `Impl`
3. Constructor tiene argumentos incorrectos

**Solución:**
- Verifica que `ShortTermRAS/dynreact/snapshot/SnapshotProviderImpl.py` existe
- Clase debe llamarse `RasSnapshotProviderImpl` (termina en `Impl`)
- Constructor: `__init__(self, provider_url: str, site: Site)`

## Backward Compatibility

El código mantiene compatibilidad backward:
- `default+file:` sigue funcionando con `FileSnapshotProvider` hardcodeado
- `ras+file:` usa Container (carga desde ShortTermRAS si está disponible)
- Profiles custom pueden agregar sus propias implementaciones

## Ejemplo Completo: Usar RAS

1. **Instala ShortTermRAS** en el entorno

2. **Configura variables de entorno**:
```bash
export PROFILE=ras
export SNAPSHOT_PROVIDER=ras+file:../../data/snapshots
export CONFIG_PROVIDER=ras+file:../../data/config/site.json
```

3. **Inicia la aplicación**:
```bash
cd OSS_Platform/DynReActService
python -m uvicorn run:fastapi_app --host 192.168.110.68 --reload --log-level debug
```

4. **Verifica logs**:
```
INFO: Loading profile 'ras'
INFO: Using RasSnapshotProviderImpl
INFO: Using RasConfigurationProviderImpl
```

## Preguntas Frecuentes

**P: ¿Puedo tener múltiples profiles instalados?**
A: Sí. Elige uno en tiempo de ejecución con `PROFILE=ras` u `PROFILE=oss`

**P: ¿Qué pasa si RAS no está instalado pero PROFILE=ras?**
A: El Container intenta cargar `ras.dynreact.snapshot`, falla, y fallback a `dynreact.snapshot` (OSS default)

**P: ¿Cómo creo un profile personalizado?**
A: Crea un paquete con la misma estructura de directorios (`{package}/dynreact/{component}/`) y usa `PROFILE={package_name}`

**P: ¿Puedo mezclar componentes de diferentes profiles?**
A: No, actualmente solo puedes tener un profile activo. Para mezclar, implementa la lógica en tu profile específico.
