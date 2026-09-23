import json
from copy import deepcopy

import pytest

from shadowbane_lab.client_extension.condemn_wire import Target
from shadowbane_lab.client_observation.native_city_registry import read_native_city_registry
from shadowbane_lab.manager import condemn_plan as module
from shadowbane_lab.manager.condemn_cycle import CondemnContext
from shadowbane_lab.manager.vendor_job import VendorJobStore
from tests.test_condemn_cycle import OWNER
from tests.test_condemn_transaction import BEFORE, LIFE, Flow
from tests.test_native_city_registry import fixture as registry_memory


def nearby(store):
    roster = dict(
        schema_version=1,
        scope="active_city_command_cached_nearby_buildings",
        process_id=LIFE.process_id,
        process_creation_filetime_utc=LIFE.creation,
        town_membership_verified=False,
        roster_complete=False,
        server_response_verified=False,
        management_permission_verified=False,
        command_admitted=False,
        buildings=[
            dict(
                building=dict(object_id=100, object_type=8),
                display_name="Tower",
                hirelings=[
                    dict(hireling=dict(object_id=300, object_type=37), display_name="Guard")
                ],
            ),
            dict(
                building=dict(object_id=200, object_type=8),
                display_name="Shop",
                hirelings=[dict(hireling=dict(object_id=400, object_type=42), display_name="Sage")],
            ),
        ],
    )
    return dict(
        schema_version=1,
        operation_id="operation-" + "a" * 32,
        state="complete",
        identity=list(store.identity),
        game_process_id=LIFE.process_id,
        game_creation_filetime=LIFE.creation,
        scene=LIFE.scene_epoch,
        root=BEFORE.root,
        buildings=2,
        hirelings=2,
        roster=roster,
    )


@pytest.fixture
def setup(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    plans = module.CondemnPlanStore(store)
    preparation = "operation-" + "a" * 32
    context = CondemnContext(LIFE, BEFORE.root)
    registry = read_native_city_registry(registry_memory())
    summary = plans.prepare(preparation, context, OWNER, nearby(store), registry)
    return store, plans, preparation, summary


def test_preparation_keeps_distinct_roles_and_only_guard_building_candidates(setup):
    _, plans, preparation, summary = setup
    assert summary == plans.current()
    assert summary["buildings"] == [dict(building=[100, 8], name="Tower", guards=1)]
    assert [e["token"] for e in summary["catalog"]["entries"]] == ["4:51", "4:101", "5:20"]
    assert summary["catalog"]["city_count"] == 2
    assert not summary["town_coverage_verified"]
    assert not summary["catalog"]["nation_inheritance_verified"]
    selection = plans.select(preparation, summary["sha256"], ["5:20", "4:51"], [100])
    targets = [Target.decode(bytes.fromhex(t)) for t in selection["targets"]]
    assert targets == [Target((100, 8), (51, 23), 4), Target((100, 8), (20, 23), 5)]


def test_same_numeric_key_in_both_roles_is_never_merged():
    registry = read_native_city_registry(registry_memory())
    registry["cities"][0]["guild"]["key"]["object_id"] = 20
    catalog = module.catalog_entries(registry)
    assert {e["token"] for e in catalog["entries"]} == {"4:20", "4:51", "5:20"}
    assert len(next(e for e in catalog["entries"] if e["token"] == "5:20")["cities"]) == 2


def test_unknown_names_and_missing_keys_never_invent_an_identity():
    registry = read_native_city_registry(registry_memory())
    registry["cities"][0]["guild"] = dict(key=dict(object_id=0, object_type=0), name="Unknown")
    registry["cities"][1]["guild"]["name"] = ""
    catalog = module.catalog_entries(registry)
    assert catalog["missing_roles"] == 1
    assert next(e for e in catalog["entries"] if e["token"] == "4:51")["names"] == []
    assert "Unknown" not in str(catalog)


def test_conflicting_labels_are_retained_without_changing_identity():
    registry = read_native_city_registry(registry_memory())
    registry["cities"][1]["nation"]["name"] = "Other label"
    entry = next(e for e in module.catalog_entries(registry)["entries"] if e["token"] == "5:20")
    assert entry["names"] == ["Other label", "Shared crest"]


@pytest.mark.parametrize(
    "tokens,buildings",
    [
        ([], [100]),
        (["5:20"], []),
        (["nation:20"], [100]),
        (["5:999"], [100]),
        (["5:20", "5:20"], [100]),
        (["5:20"], [100, 100]),
        (["5:20"], [200]),
        (["5:20"], [True]),
        (["5:20"], ["100"]),
        (["5:20"], [999]),
    ],
)
def test_caller_cannot_supply_unobserved_or_duplicate_targets(setup, tokens, buildings):
    _, plans, preparation, summary = setup
    with pytest.raises(ValueError):
        plans.select(preparation, summary["sha256"], tokens, buildings)


def test_source_digest_prevents_old_browser_selection_from_being_rebound(setup):
    _, plans, preparation, summary = setup
    record = plans.read(preparation)
    record["registry"]["cities"][0]["nation"]["name"] = "Changed"
    plans.path(preparation).write_text(json.dumps(record))
    with pytest.raises(module.CondemnCycleStopped, match="changed"):
        plans.select(preparation, summary["sha256"], ["5:20"], [100])


def test_pending_progress_prevents_preparing_an_executable_selection(setup):
    store, plans, preparation, summary = setup
    Flow(store.root).start()
    with pytest.raises(module.CondemnCycleStopped, match="earlier"):
        plans.select(preparation, summary["sha256"], ["5:20"], [100])


def test_history_capacity_rejects_whole_selection_without_truncating(setup, monkeypatch):
    _, plans, preparation, summary = setup
    monkeypatch.setattr(module, "MAX_ATTEMPTS", 1)
    with pytest.raises(module.CondemnCycleStopped, match="needs 2 checks"):
        plans.select(preparation, summary["sha256"], ["5:20", "4:51"], [100])


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(cache_count=3),
        lambda r: r.update(cache_freshness_verified=True),
        lambda r: r["cities"].append(deepcopy(r["cities"][0])),
        lambda r: r["cities"][0]["nation"]["key"].update(object_type=37),
        lambda r: r["cities"][0]["guild"]["key"].update(object_id=True),
    ],
)
def test_bad_catalog_is_not_silently_reduced_to_valid_rows(change):
    registry = read_native_city_registry(registry_memory())
    change(registry)
    with pytest.raises((ValueError, RuntimeError)):
        module.catalog_entries(registry)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(scene=99),
        lambda r: r.update(game_process_id=8),
        lambda r: r.update(identity=["node", "other", "instance"]),
        lambda r: r.update(buildings=1),
        lambda r: r["roster"].update(roster_complete=True),
        lambda r: r["roster"]["buildings"][1]["building"].update(object_id=100),
        lambda r: r["roster"]["buildings"][0]["hirelings"][0]["hireling"].update(object_type=0),
    ],
)
def test_invalid_building_provenance_is_rejected(setup, change):
    store, _, _, _ = setup
    record = nearby(store)
    change(record)
    with pytest.raises((ValueError, RuntimeError)):
        module.building_entries(record, store.identity, CondemnContext(LIFE, BEFORE.root))


def test_existing_preparation_is_immutable(setup):
    _, plans, preparation, _ = setup
    record = plans.read(preparation)
    before = plans.path(preparation).read_bytes()
    with pytest.raises(module.CondemnCycleStopped, match="already exists"):
        plans.prepare(
            preparation,
            CondemnContext(LIFE, BEFORE.root),
            OWNER,
            record["nearby"],
            record["registry"],
        )
    assert plans.path(preparation).read_bytes() == before


def test_legacy_cache_never_reports_accessible_or_empty_buildings(setup):
    _, plans, preparation, summary = setup
    before = plans.path(preparation).read_bytes()
    coverage = summary["coverage"]
    assert coverage["candidate_buildings"] == coverage["unverified_buildings"] == 2
    assert coverage["verified_guard_buildings"] == coverage["verified_no_guard_buildings"] == 0
    assert all(r["state"] == "unverified" and r["guards"] is None
               for r in coverage["buildings"])
    assert plans.summary(preparation)["sha256"] == summary["sha256"]
    assert plans.path(preparation).read_bytes() == before
