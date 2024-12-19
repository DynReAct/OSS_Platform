# Model

This module contains the basic domain model for the DynReAct production planning software.
It provides the definition of Equipment to be scheduled and Material as the unit of production,
as well as Orders (think production orders), which represent batches of Materials with common
properties.

The classes defined in this module are serializable and can be made accessible via a REST interface.

---

## Model class

::: dynreact.base.model.Model
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false
        members:
            - __init__



## LabeledItem class

::: dynreact.base.model.LabeledItem
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false
        members:
            - __init__




## ProcessInformation class

::: dynreact.base.model.ProcessInformation
    options:
        docstring_style: sphinx
        show_signature: true


## Process class

::: dynreact.base.model.Process
    options:
        docstring_style: sphinx
        show_signature: true



## Equipment class

::: dynreact.base.model.Equipment
    options:
        docstring_style: sphinx
        show_signature: true



## Storage class

::: dynreact.base.model.Storage
    options:
        docstring_style: sphinx
        show_signature: true



## EquipmentDowntime class

::: dynreact.base.model.EquipmentDowntime
    options:
        docstring_style: sphinx
        show_signature: true



## EquipmentAvailability class

::: dynreact.base.model.EquipmentAvailability
    options:
        docstring_style: sphinx
        show_signature: true


## Material class

::: dynreact.base.model.Material
    options:
        docstring_style: sphinx
        show_signature: true



## Order class

::: dynreact.base.model.Order
    options:
        docstring_style: sphinx
        show_signature: true



## Lot class

::: dynreact.base.model.Lot
    options:
        docstring_style: sphinx
        show_signature: true




## MaterialOrderData class

::: dynreact.base.model.MaterialOrderData
    options:
        docstring_style: sphinx
        show_signature: true


## PlanningData class

::: dynreact.base.model.PlanningData
    options:
        docstring_style: sphinx
        show_signature: true


## EquipmentStatus class

::: dynreact.base.model.EquipmentStatus
    options:
        docstring_style: sphinx
        show_signature: true





## EquipmentProduction class

::: dynreact.base.model.EquipmentProduction
    options:
        docstring_style: sphinx
        show_signature: true


## ProductionTargets class

::: dynreact.base.model.ProductionTargets
    options:
        docstring_style: sphinx
        show_signature: true



## StorageLevel class

::: dynreact.base.model.StorageLevel
    options:
        docstring_style: sphinx
        show_signature: true



## OrderAssignment class

::: dynreact.base.model.OrderAssignment
    options:
        docstring_style: sphinx
        show_signature: true



## ProductionPlanning class

::: dynreact.base.model.ProductionPlanning
    options:
        docstring_style: sphinx
        show_signature: true
        members:
            - __init__
            - get_lots
            - get_num_lots
            - get_targets


## MaterialClass class

::: dynreact.base.model.MaterialClass
    options:
        docstring_style: sphinx
        show_signature: true


## MaterialCategory class

::: dynreact.base.model.MaterialCategory
    options:
        docstring_style: sphinx
        show_signature: true


## Site class

::: dynreact.base.model.Site
    options:
        docstring_style: sphinx
        show_signature: true
        members:
            - __init__
            - get_process
            - get_process_by_id
            - get_equipment
            - get_equipment_by_name
            - get_process_equipment
            - get_storage
            - get_process_all_equipment

## Snapshot class

::: dynreact.base.model.Snapshot
    options:
        docstring_style: sphinx
        show_signature: true
        members:
             - __init__
             - get_order
             - get_material
             - get_order_lot
             - get_material_equipment
             - get_orders_equipment
             - get_material_selected_orders


## LongTermTargets class

::: dynreact.base.model.LongTermTargets
    options:
        docstring_style: sphinx
        show_signature: true
        members:
             - __init__


## MidTermTargets class

::: dynreact.base.model.MidTermTargets
    options:
        docstring_style: sphinx
        show_signature: true
        members:
             - __init__
