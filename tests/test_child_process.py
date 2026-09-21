"""The crash tests must be able to start a child from the database event loop.

This runs offline, without PostgreSQL, because the failure it guards against is
in process creation rather than in the database. On Windows a selector loop
cannot spawn a child at all, and the database tests have no choice but to use
one, so this would fail there long before any connection was attempted.
"""

import pytest

from health_assistant.adapters.persistence.event_loops import run
from tests.child_process import ChildProcessTimeoutError, run_child


def test_a_child_can_be_started_from_the_database_event_loop() -> None:
    result = run(run_child("tests.echo_child", "started"))

    assert result.returncode == 0
    assert result.stdout == "started"


def test_a_child_that_never_finishes_is_killed() -> None:
    with pytest.raises(ChildProcessTimeoutError):
        run(run_child("tests.sleeping_child", timeout=0.5))
