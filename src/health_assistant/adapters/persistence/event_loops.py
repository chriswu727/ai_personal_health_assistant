"""Event loop selection for asynchronous database work.

psycopg's async mode refuses to run on the Windows ProactorEventLoop, which is
the platform default there, and says so before it ever reaches the server. Every
entry point that opens an asynchronous database connection therefore creates a
selector-based loop.

There is no platform branch. A selector loop exists on every supported platform
and is already the default on POSIX, so one factory serves both and no type
check has to reason about which branch a platform takes.

The loop is created at entry points and never on import, so importing the domain
or the adapters does not change global asyncio state for an embedding
application.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any


def new_database_event_loop() -> asyncio.AbstractEventLoop:
    """Return a fresh loop that psycopg accepts."""
    return asyncio.SelectorEventLoop()


def run[Result](work: Coroutine[Any, Any, Result]) -> Result:
    """Run ``work`` to completion on a loop psycopg can use.

    For entry points that own the process, such as the migration environment.
    Callers already inside a running loop must not use this.
    """
    loop = new_database_event_loop()
    try:
        return loop.run_until_complete(work)
    finally:
        loop.close()
