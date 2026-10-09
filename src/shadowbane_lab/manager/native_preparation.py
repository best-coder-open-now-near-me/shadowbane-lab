"""Canonical native resources for the worker's preparation-only service."""
import time
from contextlib import ExitStack

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeClientProcessIdentity,
    _WindowsKernel,
)
from shadowbane_lab.client_extension.movement_session import NativeMovementSession
from shadowbane_lab.client_extension.movement_wire import BINDINGS, TERMINAL
from shadowbane_lab.client_observation import (
    load_bundled_native_character_population_profile,
    open_windows_native_character_population_reader,
)
from shadowbane_lab.client_observation.native_character_session import open_native_character_session
from shadowbane_lab.pve.attack_list import (
    AttackListOwner,
    AttackListStore,
    default_attack_list_root,
)
from shadowbane_lab.pve.native_actor import NativeActorCoordinator
from shadowbane_lab.pve.settings import load_pve_settings


class NativePreparationFactory:
    def __init__(self, binding):
        self.binding = binding
        self.character = None
        self.admission = lambda: False

    def __call__(self):
        stack = ExitStack()
        coordinator = None
        try:
            character = stack.enter_context(open_native_character_session(
                process_id=self.binding.game_process_id))
            binding = character.binding
            if (binding.process_id != self.binding.game_process_id
                    or binding.process_creation_filetime_utc
                    != self.binding.game_process_started_at_100ns):
                raise RuntimeError("preparation character belongs to another game lifetime")
            character.require_current()
            identity = (binding.identity.server_name, binding.identity.character_name)
            if self.character is not None and identity != self.character:
                raise RuntimeError("selected character changed; select the character again")
            self.character = identity
            settings = load_pve_settings(binding.identity)
            if not settings.buffs.enabled and not settings.tracking.enabled:
                stack.close()
                return None
            population = stack.enter_context(open_windows_native_character_population_reader(
                load_bundled_native_character_population_profile(),
                process_id=binding.process_id))
            session = NativeMovementSession(NativeClientProcessIdentity(
                binding.process_id, binding.process_creation_filetime_utc),
                self.binding.game_window_handle)
            stack.callback(session.close)
            snapshot = session.snapshot()
            if (not snapshot.flags & BINDINGS or snapshot.flags & TERMINAL
                    or snapshot.grant.scene <= 0
                    or not 0 <= _WindowsKernel().tick_count() - snapshot.tick <= 500):
                raise RuntimeError("native preparation scene is unavailable")
            lease = session.preparation_lease(snapshot.grant.scene)
            coordinator = NativeActorCoordinator(
                session=session, grant=lease, population=population,
                preparation_admission=self.admission,
                character_session=character, store=AttackListStore(
                    default_attack_list_root(), AttackListOwner(*identity)))
            if settings.buffs.enabled:
                coordinator.configure_preparation(settings.buffs)
            if settings.tracking.enabled:
                coordinator.configure_tracking(settings.tracking)
            character.require_current()
            return NativePreparationOwner(stack, session, lease, coordinator, character, settings)
        except Exception:
            # No action is submitted in this factory. Once returned, only the
            # service may close resources, after positive owner cleanup.
            try:
                if coordinator is not None:
                    coordinator.close_unopened()
            finally:
                stack.close()
            raise


class NativePreparationOwner:
    def __init__(self, resources, session, lease, coordinator, character, settings):
        self.resources, self.session, self.lease = resources, session, lease
        self.coordinator, self.character, self.settings = coordinator, character, settings

    @property
    def preparation_status(self):
        return self.coordinator.preparation_status

    @property
    def tracking_status(self):
        return self.coordinator.tracking_status

    @property
    def local_pending(self):
        return self.coordinator.local_pending

    def maintain(self):
        self.session.maintain_preparation(self.lease)

    def settings_changed(self):
        current = load_pve_settings(self.character.binding.identity)
        return (current.buffs, current.tracking) != (self.settings.buffs, self.settings.tracking)

    def step(self, *, allow_new):
        self.coordinator.tracking_step(allow_new=allow_new)
        if self.settings.buffs.enabled:
            return self.coordinator.preparation_step(allow_new=allow_new)
        return None

    def _closure(self, call):
        try:
            result = call()
        except (NativeActionChannelError, OSError, RuntimeError, ValueError):
            if not self.coordinator.close_retired_process():
                raise
        else:
            # The coordinator converts unavailable channel replies into an
            # unconfirmed result. Process retirement must not depend on an
            # exception escaping that boundary.
            if result[0] or not self.coordinator.close_retired_process():
                return result
        # OS retirement disposes local resources without a forged native receipt.
        return True, None, "The exact game process lifetime has retired."

    def finish(self, reason):
        return self._closure(lambda: self.coordinator.finish(reason))

    def inspect_owner_closure(self):
        return self._closure(self.coordinator.inspect_owner_closure)

    def close(self):
        self.resources.close()


def create_worker_preparation(binding, ledger, publisher, process):
    """Bind one service to the exact worker; no independent permit authority."""
    from .operation import WorkerOperationKind
    from .preparation_service import PersistentPreparationService

    gate = publisher.dispatch_gate()
    def intent():
        pending = ledger.pending_for(
            client_id=binding.client_id, instance_id=binding.instance_id,
            worker_id=publisher.worker_id, worker_process_id=process.process_id,
            worker_process_started_at_100ns=process.process_started_at_100ns,
            now=time.time())
        for operation in pending:
            if operation.kind in {WorkerOperationKind.STOP, WorkerOperationKind.CANCEL}:
                ledger.latch_preparation_stop(operation)
        control = ledger.inspect_preparation_control(binding.client_id, binding.instance_id)
        return (not gate.is_set()
                and (control is None or control.enabled),
                0 if control is None else control.revision)

    factory = NativePreparationFactory(binding)
    service = PersistentPreparationService(owner_factory=factory, intent=intent)
    def admission():
        if not service.admission_allowed():
            return False
        # A newly queued operation freezes proposals before supervision has had
        # a chance to reserve handoff. Passive reads/cleanup do not use this gate.
        return not ledger.pending_for(
            client_id=binding.client_id, instance_id=binding.instance_id,
            worker_id=publisher.worker_id, worker_process_id=process.process_id,
            worker_process_started_at_100ns=process.process_started_at_100ns,
            now=time.time())
    factory.admission = admission
    return service
