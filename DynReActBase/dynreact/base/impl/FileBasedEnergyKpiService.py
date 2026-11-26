import os.path
from datetime import datetime
from typing import Sequence

import pandas as pd

from dynreact.base.EnergyService import ServiceResultsFailed, EnergyPropertyServiceMetadata, EnergyKpiService
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.model_timeseries import Timeseries, csv_memory_timeseries


class CsvFileConfig:

    energy_type: str = "electric"
    property: str
    "Examples: \"energy_price\", \"co2\", \"renewables_share\""
    unit: str = ""
    "Examples: €/MWh"
    id: str
    label: str
    description: str|None=None
    col_idx: int = 1
    separator: str = ","
    index_col: int|str = 0
    skiprows: int|Sequence[int]|None=None
    _cnt: int = 0

    def __init__(self,
                 energy_type: str|None = None,
                 property: str|None = None,
                 unit: str|None =None,
                 id: str|None =None,
                 label: str|None =None,
                 description: str|None =None,
                 col_idx: int|None = None,
                 separator: str|None = None,
                 index_col: int|str|None = None,
                 skiprows: int|Sequence[int]|None=None):
        cnt = CsvFileConfig._cnt
        if energy_type is None:
            energy_type = os.getenv(f"FILE_ENERGY_PS{cnt}_TYPE", CsvFileConfig.energy_type)
        self.energy_type = energy_type
        if property is None:
            property = os.getenv(f"FILE_ENERGY_PS{cnt}_PROPERTY")
        if property is None:
            raise ValueError("Energy property not specified")
        self.property = property
        if unit is None:
            unit = os.getenv(f"FILE_ENERGY_PS{cnt}_UNIT", CsvFileConfig.unit)
        self.unit = unit
        if id is None:
            id = os.getenv(f"FILE_ENERGY_PS{cnt}_ID")
        if id is None:
            raise ValueError("Energy property id not specified")
        self.id = id
        if label is None:
            label = os.getenv(f"FILE_ENERGY_PS{cnt}_LABEL")
        if label is None:
            raise ValueError("Energy property label not specified")
        self.label=label
        if description is None:
            description = os.getenv(f"FILE_ENERGY_PS{cnt}_DESCRIPTION")
        self.description = description
        if col_idx is None:
            col_idx0 = os.getenv(f"FILE_ENERGY_PS{cnt}_COL_IDX", CsvFileConfig.col_idx)
            if col_idx0 is not None:
                col_idx = int(col_idx0)
        self.col_idx = col_idx
        if separator is None:
            separator = os.getenv(f"FILE_ENERGY_PS{cnt}_SEP", CsvFileConfig.separator)
        self.separator = separator
        if index_col is None:
            index_col = os.getenv(f"FILE_ENERGY_PS{cnt}_IDX_COL", CsvFileConfig.index_col)
            try:
                index_col = int(index_col)
            except:
                pass
        self.index_col = index_col
        if skiprows is None:
            rows0 = os.getenv(f"FILE_ENERGY_PS{cnt}_SKIP_ROWS")
            if rows0:
                skiprows = [int(r) for r in (r.strip() for r in rows0.split(",")) if r != ""]
        self.skiprows = skiprows
        CsvFileConfig._cnt += 1


class FileBasedEnergyKpiService(EnergyKpiService):

    def __init__(self, url: str, cfg: CsvFileConfig|None=None):
        super().__init__(url)
        if not url.startswith("file+") or ":" not in url:
            raise NotApplicableException
        file = url[url.index(":")+1:]
        self._file = file
        cfg = cfg or CsvFileConfig()
        self._cfg = cfg
        self._format = "csv"
        self._meta = EnergyPropertyServiceMetadata(id=cfg.id, label=cfg.label, description=cfg.description, energy_type=self._cfg.energy_type)
        self._data: pd.DataFrame|None = None

    def service(self) -> EnergyPropertyServiceMetadata:
        return self._meta

    def property(self) -> str:
        """Specify the property, such as \"energy_price\""""
        return self._cfg.property

    def unit(self) -> str:
        """Specify the unit, such as \"€/MWh\""""
        return self._cfg.unit

    def status(self) -> int:
        """
        :return: 0: service running, 1: service not available, > 10: custom error codes
        """
        raise 0 if self._data is not None or os.path.isfile(self._file) else 11

    def data(self,start: datetime|None=None, end: datetime|None=None) -> Timeseries | ServiceResultsFailed:
        return self._parse()  # TODO could parse a different file depending on the selected range

    def _parse(self) -> pd.DataFrame | ServiceResultsFailed:
        if not self._data:
            if not os.path.isfile(self._file):
                raise ValueError(f"Not a file: {self._file}")
            self._data = csv_memory_timeseries(self._file, col_idx=self._cfg.col_idx, separator=self._cfg.separator, index_col=self._cfg.index_col, skiprows=self._cfg.skiprows)
        return self._data
