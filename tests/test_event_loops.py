"""The database entry points must not hand psycopg a loop it rejects."""

import asyncio

from health_assistant.adapters.persistence.event_loops import (
    database_event_loop_policy,
    run,
)


def test_the_database_loop_is_never_a_proactor_loop() -> None:
    """psycopg refuses the Windows default loop, so this must hold on Windows."""
    loop = database_event_loop_policy().new_event_loop()
    try:
        assert "Proactor" not in type(loop).__name__
    finally:
        loop.close()


def test_the_chosen_loop_runs_work_to_completion() -> None:
    async def answer() -> int:
        await asyncio.sleep(0)
        return 7

    assert run(answer()) == 7
