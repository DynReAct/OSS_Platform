# Kafka clean-up

Deletion of the Kafka topic and consumer groups of an auction once it ends.

---


## cleanup_auction function
::: dynreact.shortterm.common.data.data_functions.cleanup_auction
    options:
        docstring_style: google
        show_signature: true
        show_source: false


See [Concurrent auctions and shared Kafka channels](shared_messaging.md) for channel ownership,
request correlation, parent restart behavior, retention, safe cleanup and Jenkins
verification. Shared parent/callback history is never purged by an auction.
