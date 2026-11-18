# short_term_planning module

This program runs the scripts required to start the general agents,
clones them for an auction with the resources indicated by the user,
and starts the auction, waiting for its completion.

The auction stop condition is order-based: when one material is confirmed, the
associated order tonnage is accumulated from the embedded `order` payload, and
its processing duration advances with the total order length rather than an
individual coil length.

---

## delete_all_topics function
::: dynreact.shortterm.short_term_planning.delete_all_topics
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false


## run_general_agents function
::: dynreact.shortterm.short_term_planning.run_general_agents
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false


## create_auction function
::: dynreact.shortterm.short_term_planning.create_auction
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false


## start_auction function
::: dynreact.shortterm.short_term_planning.start_auction
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false


## ask_results function
::: dynreact.shortterm.short_term_planning.ask_results
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false


## end_auction function
::: dynreact.shortterm.common.data.data_functions.end_auction
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false


## sleep function
::: dynreact.shortterm.short_term_planning.sleep
    options:
        docstring_style: sphinx
        show_signature: true
        show_source: false
