"""Event loop selection for asynchronous database work.

psycopg's async mode refuses to run on the Windows ProactorEventLoop, which is
the platform default there, and reports that before it ever reaches the server.
Every entry point that opens an asynchronous database connection therefore
selects a selector-based loop.

The choice is made at entry points and never on import, so importing the domain
or the adapters does not change global asyncio state for an embedding
application.
"""

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any


def database_event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Return a policy whose loops psycopg can use on this platform."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


def run[Result](work: Coroutine[Any, Any, Result]) -> Result:
    """Run ``work`` to completion on a loop psycopg can use.

    For entry points that own the process, such as the migration environment.
    Callers already inside a running loop must not use this.
    """
    loop = database_event_loop_policy().new_event_loop()
    try:
        return loop.run_until_complete(work)
    finally:
        loop.close()
