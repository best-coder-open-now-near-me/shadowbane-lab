from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.city_window_wire import Outcome, Snapshot
from shadowbane_lab.client_observation.native_city_registry import read_native_city_registry
from shadowbane_lab.manager import condemn_preparation as module
from shadowbane_lab.manager.condemn_plan import CondemnPlanStore
from shadowbane_lab.manager.vendor_job import VendorJobStore
from tests.test_condemn_cycle import OWNER
from tests.test_condemn_plan import nearby
from tests.test_condemn_transaction import BEFORE, LIFE
from tests.test_native_city_registry import fixture as registry_memory


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(
        game_process_id=LIFE.process_id,
        game_process_started_at_100ns=LIFE.creation,
        game_window_handle=1000,
    )
    operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
    roster = nearby(store)
    state = Snapshot(
        scene=LIFE.scene_epoch,
        revision=1,
        root=BEFORE.root,
        manager=200,
        hud=300,
        active_manager=200,
        mode=1,
        building_count=2,
        visible=1,
    )
    session = Mock(
        identity=NativeClientProcessIdentity(LIFE.process_id, LIFE.creation), window=1000
    )
    session.inspect.return_value = SimpleNamespace(outcome=Outcome.OBSERVED, snapshot=state)
    catalog = read_native_city_registry(registry_memory())
    values = [deepcopy((OWNER, LIFE.local, catalog)) for _ in range(2)]
    monkeypatch.setattr(module, "_run_discovery", lambda *args, **kwargs: roster)

    def run(**changes):
        return module.prepare_condemn(
            store,
            binding,
            operation,
            cancelled=lambda: False,
            session_factory=lambda _: session,
            catalog_reader=lambda _: values.pop(0),
            **changes,
        )

    return SimpleNamespace(
        store=store,
        session=session,
        run=run,
        values=values,
        state=state,
        operation=operation,
        roster=roster,
    )


def test_preparation_pins_catalog_and_nearby_source_without_hostility_actions(setup):
    result = setup.run()
    assert len(result["catalog"]["entries"]) == 3
    assert len(result["buildings"]) == 1
    assert setup.session.inspect.call_count == 2
    setup.session.close.assert_called_once_with()
    assert not (setup.store.root / "condemn-cycles").exists()
    assert CondemnPlanStore(setup.store).current() == result


@pytest.mark.parametrize("case", ["window", "character", "local", "scene", "changing"])
def test_foreign_or_changing_capture_does_not_publish_preparation(setup, case):
    from dataclasses import replace

    if case == "window":
        setup.session.window = 99
    elif case == "character":
        setup.values[1][0]["character_name"] = "Other"
    elif case == "local":
        owner, _, catalog = setup.values[1]
        setup.values[1] = owner, (21, 53), catalog
    elif case == "scene":
        setup.session.inspect.return_value.snapshot = replace(setup.state, scene=99)
    else:
        setup.session.inspect.side_effect = [
            SimpleNamespace(outcome=Outcome.OBSERVED, snapshot=setup.state),
            SimpleNamespace(outcome=Outcome.OBSERVED, snapshot=replace(setup.state, revision=2)),
        ]
    with pytest.raises(RuntimeError):
        setup.run()
    assert CondemnPlanStore(setup.store).current() is None
    setup.session.close.assert_called_once_with()
