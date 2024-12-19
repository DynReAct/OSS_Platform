# Lots optimizer

The LotsOptimizer module contains the interface specification for the mid-term planning
algorithm. It is possible to provide a custom implementation, but the DynReAct software
already contains an implementation (in the MidTermPlanning folder).

---

## OptimizationListener class


::: dynreact.base.LotsOptimizer.OptimizationListener
    options:
        docstring_style: sphinx
        show_signature: true



---

## LotsOptimizationState class

::: dynreact.base.LotsOptimizer.LotsOptimizationState
    options:
        docstring_style: sphinx
        show_signature: true
        members:
            - __init__




---

## LotsOptimizer class

::: dynreact.base.LotsOptimizer.LotsOptimizer
    options:
        docstring_style: sphinx
        show_signature: true
        members:
            - __init__
            - parameters
            - state
            - add_listener
            - remove_listener


---

## LotsOptimizationAlgo class

::: dynreact.base.LotsOptimizer.LotsOptimizationAlgo
    options:
        docstring_style: sphinx
        show_signature: true
        members:
            - __init__
            - heuristic_solution
            - due_dates_solution
            - create_instance
