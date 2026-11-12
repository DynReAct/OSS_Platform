# Dynreact ShortTermPlanning

**ShortTerm scenario from the DynReAct project**


The repository comes with a Short Term sample scenario, defined in dynreact subfolder. It does include several agent prototypes, such as

- `agents/agent.py`: Generic Agent supporting the basic concepts.

- `agents/log.py`: Log Agent, in charge for recording all the messages

- `agents/equipment.py`: Resource Agent (plants), in charge of handling the auction's bids considering the different setup status parameters.

- `agents/material.py`: Material Agent (coils), in charge of representing the status of the material and its willingness to offer for a slot in the next auction.

- `short_term_planning.py`: Command line script that creates an auction, starts it and collects its results. The scenario requires to have a Kafka broker avaliable to all the agent instances.


See [Concurrent auctions and shared Kafka channels](shared_messaging.md) for channel ownership,
request correlation, parent restart behavior, retention, safe cleanup and Jenkins
verification. Shared parent/callback history is never purged by an auction.
