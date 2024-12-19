# Dynreact ShortTermPlanning

**ShortTerm scenario from the DynReAct project**


The repository comes with a Short Term sample scenario, defined in dynreact subfolder. It does include several agent prototypes, such as

- `agent.py`: Generic Agent supporting the basic concepts.

- `log.py`: Log Agent, in charge for recording all the messages

- `equipment.py`: Resource Agent (plants), in charge of handling the auction's bids considering the different setup status parameters.

- `material.py`: Material Agent (coils), in charge of representing the status of the material and its willingness to offer for a slot in the next auction.

- `ShortTermPlanning.py`: Main script in charge of simulating several contexts for the auction. The scenario requires to have a Kafka broker avaliable to all the agent instances. To make possible to reset the broker queues a tool has been created and named clean_kafka.py.



