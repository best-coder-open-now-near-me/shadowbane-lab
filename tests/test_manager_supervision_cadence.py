from types import SimpleNamespace

import pytest

from shadowbane_lab.cli_commands.manager import _supervise_manager


def test_supervision_counts_check_duration_without_catchup_or_shutdown_delay():
    now, starts, delays = [10.0], [], []
    server = SimpleNamespace(is_running=True)
    durations = iter([0.1, 0.4, 0.05])

    def supervise():
        starts.append(now[0])
        now[0] += next(durations)
        if len(starts) == 3:
            server.is_running = False

    def sleep(delay):
        delays.append(delay)
        now[0] += delay

    _supervise_manager(SimpleNamespace(supervise=supervise), server,
                       clock=lambda: now[0], sleep=sleep)
    assert starts == pytest.approx([10, 10.25, 10.65])
    assert delays == pytest.approx([0.15, 0.0])


def test_supervision_failure_propagates_to_shutdown_revocation():
    def fail():
        raise RuntimeError("inspection failed")

    def no_sleep(_):
        raise AssertionError("must exit immediately")

    with pytest.raises(RuntimeError, match="inspection failed"):
        _supervise_manager(SimpleNamespace(supervise=fail),
                           SimpleNamespace(is_running=True), sleep=no_sleep)
