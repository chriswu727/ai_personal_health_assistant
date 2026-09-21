"""A child process that outlives its allowance, for the launcher timeout test."""

import time

if __name__ == "__main__":
    time.sleep(60)
