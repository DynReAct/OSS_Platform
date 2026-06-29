# Snapshot importer

The SnapshotImporter module defines the SnapshotImporter interface, which extends SnapshotProvider, indicating that the 
SnapshotProvider regularly imports snapshots from some external source. The methods allow the user to
check for the next scheduled snapshot import time and to trigger a new import.

---

## **SnapshotImporter** class

::: dynreact.base.SnapshotImporter.SnapshotImporter
    options:
        members_order: source
        show_signature: true
        show_source: false

