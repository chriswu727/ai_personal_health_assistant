"""A worker process that dies on purpose, for the restart tests.

Run as a subprocess. It claims one operation and then leaves through
``os._exit``, which runs no cleanup and closes nothing: as close to a crashed
worker as a test can get without sending a signal. Whether it dies before or
after committing is the difference between losing a transaction and leaving a
lease behind, and both need covering.
"""

import os
import sys
from datetime import timedelta

from health_assistant.adapters.persistence import create_database_engine, unit_of_work
from health_assistant.adapters.persistence.event_loops import run
from health_assistant.application.worker import claim_next_operation
from tests.support import at

WORKER_ID = "crashing-worker"
LEASE = timedelta(minutes=5)
CRASH_EXIT_CODE = 9


async def claim_and_die(database_url: str, *, commit_first: bool) -> None:
    engine = create_database_engine(database_url)
    if commit_first:
        async with unit_of_work(engine) as work:
            await claim_next_operation(
                work, worker_id=WORKER_ID, now=at(minutes=3), lease_duration=LEASE
            )
        # The claim is committed and the lease is now held by a process that is
        # about to stop existing.
        os._exit(CRASH_EXIT_CODE)

    async with unit_of_work(engine) as work:
        await claim_next_operation(
            work, worker_id=WORKER_ID, now=at(minutes=3), lease_duration=LEASE
        )
        # Still inside the transaction: the connection drops and the server
        # rolls it back.
        os._exit(CRASH_EXIT_CODE)


if __name__ == "__main__":
    run(claim_and_die(sys.argv[1], commit_first=sys.argv[2] == "commit"))
