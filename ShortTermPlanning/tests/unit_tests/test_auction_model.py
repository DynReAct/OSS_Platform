"""Regression tests for the GUI auction state model."""

from dynreact.auction.auction import Auction


def test_set_resul_replaces_stale_equipments() -> None:
    """Refreshing one auction must discard equipment results from older auctions."""
    auction = Auction()
    auction.resul = {
        "VEA09": [{"id": "old-job", "round": 0}],
        "VEA11": [{"id": "shared-job", "round": 0}],
    }

    auction.set_resul({
        "VEA11": [{"id": "new-job", "round": 1}],
    })

    assert auction.resul == {
        "VEA11": [{"id": "new-job", "round": 1}],
    }


def test_set_resul_deduplicates_jobs_within_one_refresh() -> None:
    """The stored result should keep one copy of identical jobs."""
    auction = Auction()
    repeated_job = {"id": "job-1", "round": 2}

    auction.set_resul({
        "VEA11": [repeated_job, repeated_job],
    })

    assert auction.resul == {
        "VEA11": [repeated_job],
    }
