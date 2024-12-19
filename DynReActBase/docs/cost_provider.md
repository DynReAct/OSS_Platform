# Cost provider

The CostProvider module defines the CostProvider class, which should be thought of as an
interface that must be implemented for each specific scheduling use-case. It contains all
the custom logic for building an objective function for schedules.

---

## **CostProvider** class

::: dynreact.base.CostProvider.CostProvider
    options:
        docstring_style: sphinx
        members_order: source
        show_signature: true
        members:
         - __init__
         - evaluate_order_assignments
         - evaluate_plant_assignments
         - objective_function
         - process_objective_function
         - equipment_status
