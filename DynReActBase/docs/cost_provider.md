# Cost provider

The CostProvider module defines the CostProvider class, an interface that must be implemented for each specific 
scheduling use-case. It contains all the custom logic for building an objective function for schedules.

---

## **CostProvider** class

::: dynreact.base.CostProvider.CostProvider
    options:
        docstring_style: sphinx
        members_order: source
        show_signature: true
        members:
         - __init__
         - transition_costs
         - assignment_costs
         - logistic_costs
         - structure_costs_parameter
         - priority_costs_parameter
         - path_dependent_costs
         - evaluate_order_assignments
         - evaluate_plant_assignments
         - update_transition_costs
         - objective_function
         - process_objective_function
         - equipment_status
         - relevant_fields
