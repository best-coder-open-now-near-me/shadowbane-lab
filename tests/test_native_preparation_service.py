from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from shadowbane_lab.manager import native_preparation as module


@pytest.fixture
def resources(monkeypatch):
    events = []
    binding = SimpleNamespace(game_process_id=12, game_process_started_at_100ns=34,
                              game_window_handle=56)
    native = SimpleNamespace(process_id=12, process_creation_filetime_utc=34,
        identity=SimpleNamespace(server_name="server", character_name="character"))
    character = SimpleNamespace(binding=native, require_current=lambda: None)
    @contextmanager
    def opened(**kwargs):
        yield character
        events.append("character-close")
    @contextmanager
    def population(*args, **kwargs):
        yield object()
        events.append("population-close")
    class Session:
        def __init__(self, identity, window):
            self.identity, self.window = identity, window
        def snapshot(self):
            return SimpleNamespace(flags=1, grant=SimpleNamespace(scene=7), tick=100)
        def preparation_lease(self, scene):
            events.append(("lease", scene))
            return object()
        def close(self):
            events.append("producer-close")
    class Coordinator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            events.append("ticket-open")
        def configure_preparation(self, settings):
            events.append("manifest-open")
        def close_unopened(self):
            events.append("unopened-close")
    monkeypatch.setattr(module, "open_native_character_session", opened)
    monkeypatch.setattr(module, "open_windows_native_character_population_reader", population)
    monkeypatch.setattr(
        module, "load_bundled_native_character_population_profile", lambda: object())
    monkeypatch.setattr(module, "load_pve_settings",
                        lambda _: SimpleNamespace(buffs=SimpleNamespace(enabled=True)))
    monkeypatch.setattr(module, "NativeMovementSession", Session)
    monkeypatch.setattr(module, "NativeActorCoordinator", Coordinator)
    monkeypatch.setattr(module, "_WindowsKernel", lambda: SimpleNamespace(tick_count=lambda: 150))
    monkeypatch.setattr(module, "default_attack_list_root", lambda: "unused")
    monkeypatch.setattr(module, "AttackListStore", lambda *a: object())
    return binding, character, Session, Coordinator, events


def test_background_factory_needs_scene_not_movement_ready_or_foreground(resources):
    binding, _, _, _, events = resources
    factory = module.NativePreparationFactory(binding)
    factory.admission = lambda: False
    owner = factory()
    assert ("lease", 7) in events
    assert not owner.coordinator.kwargs["preparation_admission"]()
    # No acquire, target, foreground, geometry or input API exists in this fixture.
    owner.close()
    assert events[-3:] == ["producer-close", "population-close", "character-close"]


def test_configure_failure_disposes_only_unopened_native_views(resources, monkeypatch):
    binding, _, _, coordinator, events = resources
    def failed(self, settings):
        events.append("manifest-open")
        raise ValueError("manifest failed")
    monkeypatch.setattr(coordinator, "configure_preparation", failed)
    with pytest.raises(ValueError, match="manifest failed"):
        module.NativePreparationFactory(binding)()
    assert events.count("unopened-close") == 1
    assert events.index("unopened-close") < events.index("producer-close")


def test_final_character_recheck_disposes_unopened_views(resources):
    binding, character, _, _, events = resources
    calls = []
    def current():
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("character changed")
    character.require_current = current
    with pytest.raises(ValueError, match="character changed"):
        module.NativePreparationFactory(binding)()
    assert events.count("unopened-close") == 1
    assert events.count("producer-close") == 1


def test_replaced_process_rejected_before_producer(resources):
    binding, character, _, _, events = resources
    character.binding.process_creation_filetime_utc = 999
    with pytest.raises(RuntimeError, match="lifetime"):
        module.NativePreparationFactory(binding)()
    assert not any(isinstance(x, tuple) and x[0] == "lease" for x in events)


def test_stale_scene_rejected_before_claim(resources, monkeypatch):
    binding, _, session, _, events = resources
    monkeypatch.setattr(session, "snapshot", lambda _: SimpleNamespace(
        flags=1, grant=SimpleNamespace(scene=7), tick=0))
    monkeypatch.setattr(module, "_WindowsKernel", lambda: SimpleNamespace(tick_count=lambda: 700))
    with pytest.raises(RuntimeError, match="scene"):
        module.NativePreparationFactory(binding)()
    assert "ticket-open" not in events



def test_unopened_disposal_error_still_closes_all_transport_readers(resources, monkeypatch):
    binding, _, _, coordinator, events = resources
    def configure(self, settings):
        raise ValueError("manifest failed")
    def failed_close(self):
        events.append("unopened-close")
        raise OSError("ticket close failed")
    monkeypatch.setattr(coordinator, "configure_preparation", configure)
    monkeypatch.setattr(coordinator, "close_unopened", failed_close)
    with pytest.raises(OSError, match="ticket close failed") as error:
        module.NativePreparationFactory(binding)()
    assert isinstance(error.value.__context__, ValueError)
    assert events.count("unopened-close") == 1
    assert events[-3:] == ["producer-close", "population-close", "character-close"]



@pytest.mark.parametrize("flags,tick,scene,ready", [
    (129,100,7,True), (385,100,7,False), (1,100,7,False),
    (129,0,7,False), (129,101,7,False), (137,100,7,False), (129,100,0,False),
])
def test_handoff_read_uses_positive_native_known_bit_and_fresh_scene(
        resources, monkeypatch, flags, tick, scene, ready):
    from shadowbane_lab.client_extension import movement_session, movement_wire
    binding, _, _, _, events = resources
    monkeypatch.setattr(movement_wire, "PREPARATION_KNOWN", 128, raising=False)
    monkeypatch.setattr(movement_wire, "ITEM_PREPARATION_PENDING", 256, raising=False)
    now = 600 if tick == 0 else 100
    monkeypatch.setattr(module, "_WindowsKernel", lambda: SimpleNamespace(tick_count=lambda: now))
    def read(identity, window):
        assert (identity.process_id, identity.creation_filetime_utc, window) == (12,34,56)
        return SimpleNamespace(flags=flags, tick=tick, grant=SimpleNamespace(scene=scene))
    monkeypatch.setattr(movement_session, "read_snapshot", read)
    assert module.NativePreparationFactory(binding).handoff_ready() is ready
    assert events == []


@pytest.mark.parametrize("retired", [False, True])
def test_mapping_loss_needs_positive_exact_process_retirement_before_disposal(retired):
    def failed():
        raise OSError("mapping unavailable")
    coordinator = SimpleNamespace(inspect_owner_closure=failed,
                                   close_retired_process=lambda: retired)
    owner = module.NativePreparationOwner(None, None, None, coordinator, None, None)
    if retired:
        confirmed, receipt, detail = owner.inspect_owner_closure()
        assert confirmed and receipt is None and "lifetime has retired" in detail
    else:
        with pytest.raises(OSError, match="mapping unavailable"):
            owner.inspect_owner_closure()
