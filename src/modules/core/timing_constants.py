"""
Centralized timing constants for polling/backoff loops.

These are **defaults** only. They exist to remove scattered magic numbers and
make intent explicit, while keeping behavior unchanged.
"""

# Short backoff after transient loop errors
SLEEP_ON_LOOP_ERROR_SECONDS = 5

# Typical poll/refresh cadences
SLEEP_1S = 1
SLEEP_2S = 2
SLEEP_5S = 5
SLEEP_10S = 10
SLEEP_30S = 30
SLEEP_60S = 60
SLEEP_5MIN = 300
SLEEP_1H = 3600

