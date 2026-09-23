"""Capture one exact character/area's cached crest and guard-building selection."""

from __future__ import annotations

import time
from dataclasses import asdict

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.city_window_wire import Outcome
from shadowbane_lab.client_extension.condemn_evidence import Lifetime
from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_navigation_wire import IN_FLIGHT, UNRESOLVED
from shadowbane_lab.client_observation.native_character_config import NativeCharacterConfigReader
from shadowbane_lab.client_observation.native_city_registry import read_native_city_registry
from shadowbane_lab.record_store import exclusive_record_lock

from .condemn_cycle import CondemnContext, CondemnCycleStopped
from .condemn_plan import CondemnPlanStore
from .guard_discovery import (
    read_guard_candidates,
    read_guard_roster,
    run_guard_building_discovery,
)
from .guard_owner import read_guard_owner, require_owner
from .vendor_discovery import _memory, _run_discovery, open_city_session
from .vendor_navigation import open_navigation_session


def read_condemn_catalog(binding):
    memory = _memory(binding)
    try:
        reader = NativeCharacterConfigReader(memory)
        owner = asdict(reader.observe())
        local = reader.observe_local_key()
        registry = read_native_city_registry(memory)
        require_owner(owner, asdict(reader.observe()))
        if reader.observe_local_key() != local:
            raise CondemnCycleStopped("The local character changed during catalog capture.")
        return owner, (local.object_type, local.object_uuid), registry
    finally:
        memory.close()


def prepare_condemn(
    store,
    binding,
    operation,
    *,
    cancelled,
    session_factory=open_city_session,
    candidate_reader=read_guard_candidates,
    navigation_session_factory=None,
    roster_reader=read_guard_roster,
    owner_reader=read_guard_owner,
    catalog_reader=read_condemn_catalog,
    clock=time.monotonic,
    sleep=time.sleep,
):
    CondemnProgressStore(store.root).assert_idle()
    GuardSpendingJournal(store.root).assert_idle()
    owner, local, _ = catalog_reader(binding)
    session = session_factory(binding)
    try:
        if (
            session.identity
            != NativeClientProcessIdentity(
                binding.game_process_id, binding.game_process_started_at_100ns
            )
            or session.window != binding.game_window_handle
        ):
            raise CondemnCycleStopped("The crest preparation observer owns another client.")
        nearby = _run_discovery(
            store,
            binding,
            operation,
            session,
            cancelled=cancelled,
            reader=candidate_reader,
            clock=clock,
            sleep=sleep,
            guard=True,
        )
        with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
            CondemnProgressStore(store.root).assert_idle()
            GuardSpendingJournal(store.root).assert_idle()
            if cancelled():
                raise CondemnCycleStopped("Crest preparation cancelled.")
            session.renew_lease()
            before = session.inspect()
            observed_owner, observed_local, registry = catalog_reader(binding)
            after = session.inspect()
            require_owner(owner, observed_owner)
            if (
                before.outcome != Outcome.OBSERVED
                or after.outcome != Outcome.OBSERVED
                or before.snapshot != after.snapshot
                or after.snapshot.empty
                or not after.snapshot.opened
                or after.snapshot.loading
                or (after.snapshot.scene, after.snapshot.root) != (nearby["scene"], nearby["root"])
                or observed_local != local
            ):
                raise CondemnCycleStopped("The character or area changed during crest preparation.")
            if cancelled():
                raise CondemnCycleStopped("Crest preparation cancelled.")
            context = CondemnContext(
                Lifetime(
                    binding.game_process_id,
                    binding.game_process_started_at_100ns,
                    after.snapshot.scene,
                    local,
                ),
                after.snapshot.root,
            )
    finally:
        session.close()

    # Release City Command's producer before acquiring the navigation producer.
    journal = GuardSpendingJournal(store.root)
    journal.assert_idle()
    navigation = (
        open_navigation_session(binding, journal=journal)
        if navigation_session_factory is None else navigation_session_factory(binding)
    )
    try:
        if navigation.identity != session.identity or navigation.window != session.window:
            raise CondemnCycleStopped("The roster observer owns another client.")

        def checked_cancelled():
            if cancelled():
                return True
            require_owner(owner, owner_reader(binding))
            return False

        rosters = run_guard_building_discovery(
            store, binding, operation, navigation, nearby,
            cancelled=checked_cancelled, reader=roster_reader,
            clock=clock, sleep=sleep, roster_only=True,
        )
        with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
            CondemnProgressStore(store.root).assert_idle()
            journal.assert_idle()
            if checked_cancelled():
                raise CondemnCycleStopped("Crest preparation cancelled.")
            navigation.renew_lease()
            before = navigation.inspect()
            observed_owner, observed_local, registry = catalog_reader(binding)
            after = navigation.inspect()
            require_owner(owner, observed_owner)
            if (
                before.outcome != Outcome.OBSERVED or after.outcome != Outcome.OBSERVED
                or before.snapshot != after.snapshot or after.snapshot.empty
                or (before.flags | after.flags) & (IN_FLIGHT | UNRESOLVED)
                or (after.snapshot.scene, after.snapshot.root) != (nearby["scene"], nearby["root"])
                or observed_local != local
            ):
                raise CondemnCycleStopped("The character or area changed during roster capture.")
            return CondemnPlanStore(store).prepare(
                operation.operation_id, context, owner, nearby, registry, rosters=rosters
            )
    finally:
        navigation.close()
