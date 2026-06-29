# Shifts provider

The ShiftsProvider module defines the ShiftsProvider interface, importing shifts information from an external data source. 
While a custom implementation is indispensable for productive use, a dummy implementation is provided for test
and development purposes. It can be activated via the environment variable

```
SHIFTS_PROVIDER=dummy:default
```

By default, it reports all equipments to be available all the time (in three shifts of 8h duration per day), 
but it can also be configured to add random downtimes, with optional random seed:

```
SHIFTS_PROVIDER=dummy:rand(42)
```

---

## **ShiftsProvider** class

::: dynreact.base.ShiftsProvider.ShiftsProvider
    options:
        members_order: source
        show_signature: true
        show_source: false


