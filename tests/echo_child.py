"""A child process that echoes its argument, for the launcher smoke test."""

import sys

if __name__ == "__main__":
    sys.stdout.write(sys.argv[1])
