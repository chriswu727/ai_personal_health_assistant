"""Launching a child process from a loop that cannot spawn one.

The database tests run on a selector event loop because psycopg refuses the
Windows proactor loop. Windows selector loops, in turn, do not implement asyncio
subprocess transports, so `asyncio.create_subprocess_exec` fails there before a
child ever starts.

Launching through a worker thread keeps process creation off the event loop
entirely, so one path works on every supported platform and the database tests
keep the loop they need.
"""

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 30.0


class ChildProcessTimeoutError(RuntimeError):
    """A child outlived its allowance and was killed."""


@dataclass(frozen=True, slots=True)
class CompletedChild:
    """What a finished child process left behind."""

    returncode: int
    stdout: str
    stderr: str


def _launch(module: str, arguments: tuple[str, ...], timeout: float) -> CompletedChild:
    command = [sys.executable, "-m", module, *arguments]
    try:
        completed = subprocess.run(  # noqa: S603 - the command is this interpreter and a module name, never user input
            command,
            cwd=str(REPOSITORY_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        # subprocess.run has already killed and reaped the child by this point,
        # so a worker that hangs cannot hold the test open.
        message = f"{module} did not finish within {timeout} seconds"
        raise ChildProcessTimeoutError(message) from expired
    return CompletedChild(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


async def run_child(
    module: str, *arguments: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> CompletedChild:
    """Run ``module`` as a child process and return what it produced."""
    return await asyncio.to_thread(_launch, module, arguments, timeout)
