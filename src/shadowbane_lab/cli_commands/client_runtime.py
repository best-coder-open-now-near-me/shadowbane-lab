"""Shared live-client command guards and action metadata."""

from __future__ import annotations

import time

from shadowbane_lab.client_input import (
    ArcaneClientAction,
    ForegroundWindowGuard,
    WindowGuardError,
    WindowSnapshot,
)

_PVE_TARGET_ACTIONS = (
    (
        "client.pve.target_next_mobile",
        "Target Next Mob",
        ArcaneClientAction.TARGET_NEXT_MOB,
    ),
    (
        "client.pve.target_previous_mobile",
        "Target Previous Mob",
        ArcaneClientAction.TARGET_PREVIOUS_MOB,
    ),
    (
        "client.pve.clear_selection",
        "Clear Target",
        ArcaneClientAction.CLEAR_TARGET,
    ),
)


def _wait_for_guarded_client(
    guard: ForegroundWindowGuard,
    *,
    wait_seconds: float,
) -> WindowSnapshot:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return guard.require_target()
        except WindowGuardError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.1, remaining))


def _require_window_process_id(snapshot: WindowSnapshot) -> int:
    if snapshot.process_id is None:
        raise WindowGuardError("foreground process identity is unavailable")
    return snapshot.process_id
