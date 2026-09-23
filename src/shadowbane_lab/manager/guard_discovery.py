"""Guard discovery uses exact typed navigation and retains incomplete coverage."""
from __future__ import annotations

import time

from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_observation.native_building_hirelings import (
    read_native_building_hirelings,
)
from shadowbane_lab.client_observation.native_guard_upgrade import read_native_guard_upgrade
from shadowbane_lab.client_observation.native_nearby_vendor_roster import (
    read_native_nearby_hirelings,
)

from .vendor_discovery import _memory, _run_discovery, open_city_session
from .vendor_navigation import _run_building_discovery, open_navigation_session


def read_guard_roster(binding, *, window):
    if window not in ("building", "guard"):
        raise ValueError("invalid guard discovery window")
    memory = _memory(binding)
    try:
        reader = (
            read_native_building_hirelings if window == "building" else read_native_guard_upgrade
        )
        return reader(memory)
    finally:
        memory.close()


def run_guard_building_discovery(
    store, binding, operation, session, nearby, *, cancelled,
    reader=read_guard_roster, clock=time.monotonic, sleep=time.sleep, remembered=(),
    roster_only=False,
):
    """Visit candidates once under one producer lease, without gold or upgrade actions.

    Discovery records are separate from vendor records under the same worker
    execution lock. A completed candidate list never means full town coverage.
    The submitting session must stay alive until each correlated response arrives.
    """
    return _run_building_discovery(
        store, binding, operation, session, nearby, cancelled=cancelled,
        reader=reader, clock=clock, sleep=sleep, guard=True, remembered=remembered,
        roster_only=roster_only,
    )


def read_guard_candidates(binding):
    memory = _memory(binding)
    try:
        return read_native_nearby_hirelings(memory)
    finally:
        memory.close()


def run_guard_discovery(
    store, binding, operation, *, cancelled,
    city_session_factory=open_city_session,
    navigation_session_factory=None,
    candidate_reader=read_guard_candidates, roster_reader=read_guard_roster,
    clock=time.monotonic, sleep=time.sleep, remembered=(),
):
    """Discover nearby candidates then inspect each owned guard window.

    The exact worker owns admission. This runner sends navigation only, never
    gold or upgrade commands. Each stage records intent before dispatch. Session
    handoff occurs only after the previous stage completes, respecting the single
    producer lease; failure never proceeds to the next stage or replays an open.
    """
    journal = GuardSpendingJournal(store.root)
    journal.assert_idle()
    city = city_session_factory(binding)
    try:
        nearby = _run_discovery(
            store, binding, operation, city, cancelled=cancelled,
            reader=candidate_reader, clock=clock, sleep=sleep, guard=True,
        )
    finally:
        city.close()
    navigation = (
        open_navigation_session(binding, journal=journal)
        if navigation_session_factory is None else navigation_session_factory(binding)
    )
    try:
        return run_guard_building_discovery(
            store, binding, operation, navigation, nearby, cancelled=cancelled,
            reader=roster_reader, clock=clock, sleep=sleep, remembered=remembered,
        )
    finally:
        navigation.close()
