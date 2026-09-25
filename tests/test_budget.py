"""The run budget must stop a run even when the alarm lands inside a network read."""
from __future__ import annotations

import time

import httpx
import pytest

from collector import __main__ as cli
from collector.http import NETWORK_FAULTS


def test_over_budget_is_not_a_network_fault():
    """httpcore turns a TimeoutError inside a socket read into httpx.ReadTimeout, which the session retries —
    that swallowed the alarm on 25 Sep 2026. The budget's exception must be none of those."""
    assert not issubclass(cli.OverBudget, Exception)
    assert not issubclass(cli.OverBudget, NETWORK_FAULTS)


def test_budget_interrupts_a_catch_all_retry_loop():
    def stubborn():                          # a module/source that retries on anything, like a slow read under retry
        while True:
            try:
                time.sleep(0.05)
            except Exception:
                continue
    with pytest.raises(cli.OverBudget):
        with cli.Budget(1):
            stubborn()


def test_budget_survives_httpx_exception_mapping():
    from httpcore._exceptions import map_exceptions
    import socket

    def read():
        with map_exceptions({socket.timeout: httpx.ReadTimeout, OSError: httpx.ReadError}):
            while True:
                time.sleep(0.05)
    with pytest.raises(cli.OverBudget):
        with cli.Budget(1):
            read()
