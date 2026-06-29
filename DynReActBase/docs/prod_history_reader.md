# Production history reader

The ProductionHistoryReader module defines the ProductionHistoryReader interface, importing aggregated
past production statistics from an external data source.
While a custom implementation is indispensable for productive use, a dummy implementation is provided for test
and development purposes. It can be activated via the environment variable

```
HISTORY_READER=dummy:default
```

It assumes all equipment to have been operating at full capacity all the time, not taking into account shifts or downtimes.

---

## **ProductionHistoryReader** class

::: dynreact.base.ProductionHistoryReader.ProductionHistoryReader
    options:
        members_order: source
        show_signature: true
        show_source: false


