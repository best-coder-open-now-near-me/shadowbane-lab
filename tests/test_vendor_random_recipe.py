import copy
import hashlib
import json
import uuid
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.action_channel import NativeActionChannelUnavailable
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, fill_available_slots
from shadowbane_lab.client_extension.vendor_completion import (
    keep_completed_batch,
    validate_completed_batch,
    validate_completed_keep,
)
from shadowbane_lab.client_extension.vendor_menu_wire import Snapshot as MenuSnapshot
from shadowbane_lab.client_extension.vendor_recipe import RandomRecipeSpec
from shadowbane_lab.client_extension.vendor_session import NativeVendorSession
from shadowbane_lab.client_extension.vendor_wire import Command, Host, Slot, Snapshot, Verb
from tests.test_vendor_batch import KEY, Session
from tests.test_vendor_completion import KeepSession
from tests.test_vendor_session import Transport

SPEC = RandomRecipeSpec(25860, 16)


class RandomSession(Session):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        self.state = replace(self.state, item_template=SPEC.template, table=SPEC.table)
        self.general_inspections = 0
        self.general_creates = 0

    def inspect_random(self):
        self.general_inspections += 1
        return super().inspect()

    def create_random(self, expected, key):
        self.general_creates += 1
        assert json.loads(self.path.read_bytes())["schema_version"] == 3
        return super().create(expected, key)

    def create(self, expected, key):
        raise AssertionError("generalized batch used legacy Create")

    def inspect(self):
        raise AssertionError("generalized batch used legacy inspection")


def preparation_for(session, *, spec=SPEC):
    s = session.state
    menu = MenuSnapshot(
        **{name: getattr(s, name) for name in (
            "scene", "revision", "root", "manager", "menu", "hireling", "building", "vendor",
            "recipe", "inventory", "item_template", "prefix", "suffix", "mode", "table",
            "quantity", "multiple",
        )}, front_hud=s.recipe, selected_template=s.item_template,
        activated_template=s.item_template, sentinel=3362971591, recipe_list=800,
    )
    raw = dict(schema_version=1, operation="prepare_recipe", state="complete",
               operation_id=str(uuid.uuid4()), process_id=session.identity.process_id,
               process_creation_filetime_utc=session.identity.creation_filetime_utc, window=1000,
               expected_owner=menu.encode().hex(), initial_snapshot=menu.encode().hex(),
               final_snapshot=menu.encode().hex(), requested_recipe=spec.as_dict(), requests=[])
    return (json.dumps(raw, indent=2) + "\n").encode()


def run(session, *, preparation=None, spec=SPEC, **kwargs):
    return fill_available_slots(
        session, session.path, session.state.vendor, recipe=spec,
        preparation_raw=(preparation if preparation is not None
                         else preparation_for(session, spec=spec)),
        **kwargs,
    )


def test_spec_is_immutable_canonical_and_exact():
    assert RandomRecipeSpec.from_dict(SPEC.as_dict()) == SPEC
    assert len(SPEC.canonical_digest) == 64
    assert RandomRecipeSpec(5051080, 16).canonical_digest != SPEC.canonical_digest
    assert RandomRecipeSpec(25860, 12).canonical_digest != SPEC.canonical_digest
    with pytest.raises(FrozenInstanceError):
        SPEC.table = 12


@pytest.mark.parametrize("template,table", [(0, 1), (1, 0), (True, 16), (25860, False),
                                           (-1, 16), (25860, 2**32)])
def test_invalid_recipe_scalar_rejected(template, table):
    with pytest.raises(ValueError):
        RandomRecipeSpec(template, table)


@pytest.mark.parametrize("field,value", [("mode", True), ("mode", 2), ("quantity", 2),
    ("multiple", 0), ("multiple", True), ("sentinel", 0), ("prefix", 0), ("suffix", 0),
    ("unexpected", 1)])
def test_recipe_dict_never_adopts_changed_or_loosely_typed_intent(field, value):
    raw = SPEC.as_dict()
    raw[field] = value
    with pytest.raises(ValueError):
        RandomRecipeSpec.from_dict(raw)


def test_typed_template_required():
    raw = SPEC.as_dict()
    raw["template"]["object_type"] = False
    with pytest.raises(ValueError):
        RandomRecipeSpec.from_dict(raw)


def test_generalized_batch_preserves_exact_preparation_and_uses_new_verbs(tmp_path):
    session = RandomSession(tmp_path / "create.json")
    preparation = preparation_for(session)
    record = run(session, preparation=preparation)
    assert record["state"] == "complete" and record["schema_version"] == 3
    assert record["preparation_journal_utf8"].encode() == preparation
    assert record["preparation_sha256"] == hashlib.sha256(preparation).hexdigest()
    assert record["recipe_spec_sha256"] == SPEC.canonical_digest
    assert session.general_creates == 2 and session.general_inspections >= 3
    assert validate_completed_batch(session.path.read_bytes())[0] == record
    with pytest.raises(VendorBatchStopped, match="replay"):
        run(session)
    assert session.general_creates == 2


@pytest.mark.parametrize("change", ["table", "template", "owner", "window", "lifetime",
                                    "pending", "optional_table", "recipe_window"])
def test_wrong_preparation_fails_before_any_create(tmp_path, change):
    session = RandomSession(tmp_path / "create.json")
    preparation = json.loads(preparation_for(session))
    if change in ("table", "template"):
        other = (RandomRecipeSpec(5051080, 16) if change == "template"
                 else RandomRecipeSpec(25860, 12))
        preparation["requested_recipe"] = other.as_dict()
    elif change == "owner":
        session.state = replace(session.state, vendor=123)
    elif change == "window":
        preparation["window"] += 1
    elif change == "lifetime":
        preparation["process_creation_filetime_utc"] += 1
    elif change == "pending":
        preparation["state"] = "review"
    elif change == "optional_table":
        preparation["requested_recipe"]["table"] = None
    else:
        session.state = replace(session.state, recipe=404)
    with pytest.raises(ValueError):
        run(session, preparation=json.dumps(preparation).encode())
    assert session.general_creates == 0 and not session.path.exists()


def test_old_runtime_cannot_begin_generalized_batch(tmp_path):
    session = RandomSession(tmp_path / "create.json")
    session.inspect_random = lambda: (_ for _ in ()).throw(
        NativeActionChannelUnavailable("unknown_command_kind"))
    with pytest.raises(NativeActionChannelUnavailable):
        run(session)
    assert session.general_creates == 0 and not session.path.exists()


def test_recipe_change_between_creates_stops_before_second_send(tmp_path):
    session = RandomSession(tmp_path / "create.json")
    preparation = preparation_for(session)

    def change():
        if session.general_creates:
            session.state = replace(session.state, table=12)

    with pytest.raises(VendorBatchStopped):
        run(session, preparation=preparation, before_action=change)
    assert session.general_creates == 1


@pytest.mark.parametrize("change", ["spec_digest", "preparation_hash", "prep_content",
                                    "request_recipe", "state", "removed_request", "downgrade"])
def test_completed_generalized_batch_requires_exact_spec_preparation_and_chain(tmp_path, change):
    session = RandomSession(tmp_path / "create.json")
    record = run(session)
    if change == "spec_digest":
        record["recipe_spec_sha256"] = "0" * 64
    elif change == "preparation_hash":
        record["preparation_sha256"] = "0" * 64
    elif change == "prep_content":
        prep = json.loads(record["preparation_journal_utf8"])
        prep["window"] += 1
        raw = json.dumps(prep)
        record.update(preparation_journal_utf8=raw,
                      preparation_sha256=hashlib.sha256(raw.encode()).hexdigest())
    elif change == "request_recipe":
        old = Snapshot.decode(bytes.fromhex(record["requests"][1]["expected_snapshot"]))
        record["requests"][1]["expected_snapshot"] = replace(old, table=12).encode().hex()
    elif change == "state":
        record["requests"][0]["state"] = "submitted"
    elif change == "removed_request":
        record["requests"].pop()
    else:
        record["schema_version"] = 1
    with pytest.raises(ValueError):
        validate_completed_batch(json.dumps(record).encode())


def test_lost_generalized_ack_is_never_replayed(tmp_path):
    session = RandomSession(tmp_path / "create.json", behavior="exception")
    with pytest.raises(OSError):
        run(session)
    assert json.loads(session.path.read_bytes())["state"] == "uncertain"
    with pytest.raises(VendorBatchStopped):
        run(session)
    assert session.general_creates == 1


def test_generalized_keep_retains_exact_source_hash_and_unknown_items(tmp_path):
    created = RandomSession(tmp_path / "create.json")
    batch = run(created)
    keep_path = tmp_path / "keep.json"
    session = KeepSession(created, keep_path)
    kept = keep_completed_batch(session, created.path, keep_path)
    assert kept["kept"] == batch["items"] and kept["excluded"] == []
    assert kept["source_batch_sha256"] == hashlib.sha256(created.path.read_bytes()).hexdigest()
    assert validate_completed_keep(keep_path.read_bytes(), created.path.read_bytes())["kept"] == (
        batch["items"])
    changed = copy.deepcopy(batch)
    changed["recipe_spec"]["table"] = 12
    with pytest.raises(ValueError):
        validate_completed_keep(keep_path.read_bytes(), json.dumps(changed).encode())


def test_new_wire_verbs_keep_legacy_admission_and_sizes(tmp_path):
    state = RandomSession(tmp_path / "unused").state
    command = Command(Host(1, 2, 3), 1000, KEY, state)
    assert len(command.encode(Verb.CREATE_RANDOM)) == 576
    assert len(replace(command, expected=Snapshot()).encode(Verb.INSPECT_RANDOM)) == 576
    with pytest.raises(ValueError):
        command.encode(Verb.CREATE)
    for changed in (replace(state, multiple=1), replace(state, table=0),
                    replace(state, item_template=0), replace(state, quantity=2)):
        with pytest.raises(ValueError):
            replace(command, expected=changed).encode(Verb.CREATE_RANDOM)


def test_session_probes_new_verb_without_legacy_fallback():
    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport):
        session = NativeVendorSession(RandomSession.identity, 1000)
        assert session.inspect_random().snapshot
        assert session._transport.commands[0].kind == Verb.INSPECT_RANDOM
        session.close()


def completion_for(session, batch, template):
    from tests.test_crafting_assessment import result

    capture = result()
    capture.update(process_id=session.identity.process_id,
                   process_creation_filetime_utc=session.identity.creation_filetime_utc)
    capture["message"]["vendor"] = {"object_id": session.state.vendor, "object_type": 42}
    capture["message"]["roll"].update(
        item={"object_id": batch["items"][0], "object_type": 40}, template_id=template,
    )
    return capture


@pytest.mark.parametrize("template,table", [(25860, 16), (5051080, 16), (26990, 12)])
def test_generalized_completion_keeps_unknown_without_borrowing_legacy_affix_authority(
    tmp_path, template, table,
):
    created = RandomSession(tmp_path / "create.json")
    created.state = replace(created.state, item_template=template, table=table)
    batch = run(created, spec=RandomRecipeSpec(template, table))
    capture = tmp_path / "capture.jsonl"
    capture.write_text(json.dumps(completion_for(created, batch, template)) + "\n")
    journal = tmp_path / "keep.json"
    kept = keep_completed_batch(
        KeepSession(created, journal), created.path, journal, capture=capture,
    )
    assert kept["excluded"] == []
    assert kept["decisions"][batch["items"][0]] == {
        "disposition": "keep", "reason": "unknown_affix_preserved",
    }


def test_foreign_recipe_completion_rejected_before_keep(tmp_path):
    created = RandomSession(tmp_path / "create.json")
    batch = run(created)
    capture = tmp_path / "capture.jsonl"
    capture.write_text(json.dumps(completion_for(created, batch, 26990)) + "\n")
    journal = tmp_path / "keep.json"
    session = KeepSession(created, journal)
    with pytest.raises(ValueError, match="does not belong"):
        keep_completed_batch(session, created.path, journal, capture=capture)
    assert not session.calls and not journal.exists()


def test_conflicting_generalized_completion_still_rejected_before_keep(tmp_path):
    created = RandomSession(tmp_path / "create.json")
    batch = run(created)
    first = completion_for(created, batch, SPEC.template)
    second = copy.deepcopy(first)
    second["message"]["suffix_token"] += 1
    capture = tmp_path / "capture.jsonl"
    capture.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    journal = tmp_path / "keep.json"
    session = KeepSession(created, journal)
    with pytest.raises(ValueError, match="conflicting"):
        keep_completed_batch(session, created.path, journal, capture=capture)
    assert not session.calls and not journal.exists()


def test_generalized_capacity_growth_remains_bounded_and_recoverable(tmp_path):
    created = RandomSession(tmp_path / "create.json")
    preparation = preparation_for(created)

    def grow():
        if created.general_creates == 1 and len(created.state.slots) == 2:
            created.state = replace(created.state, slots=created.state.slots + (Slot(800),))

    batch = run(created, preparation=preparation, before_action=grow)
    assert batch["capacity_history"] == [2, 3]
    assert len(batch["items"]) == created.general_creates == 3
    assert validate_completed_batch(created.path.read_bytes())[0] == batch


def test_missing_recipe_or_preparation_never_silently_falls_back(tmp_path):
    created = RandomSession(tmp_path / "create.json")
    for args in ({"recipe": SPEC}, {"preparation_raw": preparation_for(created)}):
        with pytest.raises(ValueError, match="required together"):
            fill_available_slots(created, created.path, created.state.vendor, **args)
    assert created.general_inspections == created.general_creates == 0


def test_generalized_mutation_has_no_retry_or_legacy_fallback(tmp_path):
    from shadowbane_lab.client_extension.action_channel import NativeActionChannelTimeout

    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport):
        session = NativeVendorSession(RandomSession.identity, 1000)
        seen = []

        def timeout(command, **kwargs):
            seen.append(command)
            raise NativeActionChannelTimeout("lost Create result")

        session._transport.submit = timeout
        with pytest.raises(NativeActionChannelTimeout):
            session.create_random(RandomSession(tmp_path / "unused").state, KEY)
        assert len(seen) == 1 and seen[0].kind == Verb.CREATE_RANDOM
        session.close()


def test_generalized_scepter_cannot_downgrade_into_legacy_completed_batch(tmp_path):
    created = RandomSession(tmp_path / "create.json")
    created.state = replace(created.state, item_template=26990, table=12)
    batch = run(created, spec=RandomRecipeSpec(26990, 12))
    assert validate_completed_batch(created.path.read_bytes())[0]["schema_version"] == 3
    batch["schema_version"] = 1
    with pytest.raises(ValueError, match="complete, observed"):
        validate_completed_batch(json.dumps(batch).encode())


@pytest.mark.parametrize("multiple", [False, True])
@pytest.mark.parametrize("field", ["recipe_spec", "recipe_spec_sha256",
                                   "preparation_journal_utf8", "preparation_sha256"])
def test_legacy_journal_rejects_each_generalized_evidence_field(tmp_path, multiple, field):
    from tests.test_vendor_batch import MultipleSession

    path = tmp_path / "legacy.json"
    session = MultipleSession(path) if multiple else Session(path)
    batch = fill_available_slots(session, path, session.state.vendor, sleeper=lambda _: None)
    assert validate_completed_batch(path.read_bytes())[0] == batch
    batch[field] = None
    with pytest.raises(ValueError, match="complete, observed"):
        validate_completed_batch(json.dumps(batch).encode())
