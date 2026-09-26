"""Saved per-character/vendor recipes and worker-owned non-spending selection.

Stable keys own preferences; menu pointers remain observation/visit data. Every
Start prepares the saved specification again before generalized crafting.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import replace

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, _owner
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_menu import (
    open_recipe_catalog,
    prepare_recipe,
    validate_completed_menu,
)
from shadowbane_lab.client_extension.vendor_menu_wire import READY, Outcome, Snapshot
from shadowbane_lab.client_extension.vendor_recipe import RandomRecipeSpec
from shadowbane_lab.client_observation.native_character_config import NativeCharacterConfigReader
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_vendor_recipe_catalog import (
    EXACT_EXECUTABLE_SHA256,
    read_native_vendor_recipe_catalog,
)
from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

_TOKEN = re.compile(r"[0-9a-f]{32}\Z")


def _token(value):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError("invalid saved recipe revision")
    return value


def _write(path, record):
    publish_atomic_record(
        path,
        (json.dumps(record, sort_keys=True, indent=2) + "\n").encode(),
        temporary_label="vendor-recipes",
    )


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_owner(owner):
    if not isinstance(owner, dict) or set(owner) != {"server", "character", "key"}:
        raise ValueError("invalid recipe character identity")
    for name in ("server", "character"):
        value = owner[name]
        if (
            not isinstance(value, str)
            or not 0 < len(value) <= 256
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("invalid recipe character identity")
    key = owner["key"]
    if (
        not isinstance(key, list)
        or len(key) != 2
        or type(key[0]) is not int
        or not 0 < key[0] < 2**32
        or type(key[1]) is not int
        or key[1] != 53
    ):
        raise ValueError("recipe owner requires a calibrated player key")
    return owner


def _typed(value, kind):
    if (
        not isinstance(value, dict)
        or set(value) != {"object_id", "object_type"}
        or type(value["object_id"]) is not int
        or not 0 < value["object_id"] < 2**32
        or type(value["object_type"]) is not int
        or value["object_type"] != kind
    ):
        raise ValueError("invalid saved recipe native key")
    return value


def read_context(binding, *, catalog=False):
    memory = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", binding.game_process_id)
    try:
        if (
            memory.process_creation_filetime_utc != binding.game_process_started_at_100ns
            or memory.executable_sha256 != EXACT_EXECUTABLE_SHA256
        ):
            raise VendorBatchStopped("recipe client lifetime or image changed")
        reader = NativeCharacterConfigReader(memory)
        before = reader.observe()
        key = reader.observe_local_key()
        owner = validate_owner(
            dict(
                server=before.server_name,
                character=before.character_name,
                key=[key.object_type, key.object_uuid],
            )
        )
        observation = read_native_vendor_recipe_catalog(memory) if catalog else None
        if reader.observe() != before or reader.observe_local_key() != key:
            raise VendorBatchStopped("character changed during recipe observation")
        return owner, observation
    finally:
        memory.close()


class VendorRecipeStore:
    def __init__(self, store):
        self.job_store = store
        self.root = store.root.parent.parent / "vendor-recipes"
        self.local = store.root / "recipe-selection"
        self.identity = list(store.identity[:2])

    def catalog(self, token=None):
        path = self.local / "catalog.json"
        if not path.exists():
            if token is not None:
                raise VendorBatchStopped("load this vendor's recipe list first")
            return None
        result = json.loads(_read_record(path, 512 * 1024))
        if (
            result.get("schema_version") != 1
            or result.get("identity") != list(self.job_store.identity)
            or _token(result["catalog_id"]) != (token or result["catalog_id"])
        ):
            raise VendorBatchStopped("recipe list changed; load it again")
        validate_owner(result["owner"])
        snapshot = result["snapshot"]
        _typed(snapshot["building"], 8)
        _typed(snapshot["vendor"], 42)
        rows = snapshot["recipes"]
        if not isinstance(rows, list) or len(rows) > 256:
            raise ValueError("invalid saved recipe catalog")
        seen = set()
        for row in rows:
            key = _typed(row["template"], 0)["object_id"]
            if key in seen or not isinstance(row["display_name"], str):
                raise ValueError("invalid saved recipe catalog row")
            seen.add(key)
        Snapshot.decode(bytes.fromhex(result["menu_snapshot"]))
        return result

    def read(self, revision):
        result = json.loads(
            _read_record(self.root / "revisions" / (_token(revision) + ".json"), 8192)
        )
        if (
            result.get("schema_version") != 1
            or result.get("identity") != self.identity
            or result.get("revision") != revision
        ):
            raise ValueError("invalid saved recipe record")
        validate_owner(result["owner"])
        _typed(result["building"], 8)
        _typed(result["vendor"], 42)
        spec = RandomRecipeSpec.from_dict(result["recipe_spec"])
        if result.get("recipe_sha256") != spec.canonical_digest:
            raise ValueError("saved recipe specification changed")
        if not isinstance(result.get("display_name"), str) or len(result["display_name"]) > 512:
            raise ValueError("invalid saved recipe label")
        return result

    def _preference(self, owner, building, vendor):
        return (
            self.root
            / "owners"
            / _digest(owner)
            / f"{building['object_id']}-{vendor['object_id']}.json"
        )

    def activate(self, owner, building, vendor):
        path = self._preference(owner, building, vendor)
        record = None
        if path.exists():
            revision = json.loads(_read_record(path, 256))["revision"]
            record = self.read(revision)
            if (
                record["owner"] != owner
                or record["building"] != building
                or record["vendor"] != vendor
            ):
                raise ValueError("recipe preference belongs to another owner")
        _write(self.local / "current.json", {"revision": record["revision"] if record else None})
        return record

    def current(self, revision=None):
        path = self.local / "current.json"
        if not path.exists():
            if revision is not None:
                raise VendorBatchStopped("load and save a vendor recipe first")
            return None
        current = json.loads(_read_record(path, 256))["revision"]
        if revision is not None and current != revision:
            raise VendorBatchStopped("saved recipe changed; refresh its controls")
        return self.read(current) if current else None

    def save(self, owner, building, vendor, spec, label):
        revision = uuid.uuid4().hex
        result = dict(
            schema_version=1,
            identity=self.identity,
            revision=revision,
            owner=owner,
            building=building,
            vendor=vendor,
            display_name=label,
            recipe_spec=spec.as_dict(),
            recipe_sha256=spec.canonical_digest,
        )
        _write(self.root / "revisions" / (revision + ".json"), result)
        self.read(revision)
        _write(self._preference(owner, building, vendor), {"revision": revision})
        _write(self.local / "current.json", {"revision": revision})
        return result

    def summary(self):
        catalog = self.catalog()
        current = self.current()
        return dict(
            catalog=None
            if catalog is None
            else dict(
                catalog_id=catalog["catalog_id"],
                recipes=catalog["snapshot"]["recipes"],
                vendor=catalog["snapshot"]["vendor"],
                building=catalog["snapshot"]["building"],
            ),
            saved=current,
        )


def _ready(receipt, window):
    if receipt.outcome != Outcome.OBSERVED or receipt.flags != READY or receipt.window != window:
        raise VendorBatchStopped("vendor menu is not ready")
    return receipt.snapshot


def run_recipe_selection(
    store,
    binding,
    operation,
    session,
    *,
    catalog_id=None,
    template=None,
    cancelled=lambda: False,
    reader=read_context,
):
    """One non-spending worker operation; journal each menu request before dispatch."""
    recipes = VendorRecipeStore(store)
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        CondemnProgressStore(store.root).assert_idle()
        if cancelled():
            raise VendorBatchStopped("recipe selection cancelled")
        menus = session.menu_session()
        try:

            def ready():
                deadline = time.monotonic() + 60
                while not cancelled():
                    receipt = menus.inspect()
                    if receipt.outcome == Outcome.OBSERVED and receipt.flags == READY:
                        return _ready(receipt, binding.game_window_handle)
                    if receipt.flags & 6 or time.monotonic() >= deadline:
                        raise VendorBatchStopped("return to the game; vendor menu is unavailable")
                    session.renew_lease()
                    time.sleep(0.1)
                raise VendorBatchStopped("recipe selection cancelled")

            initial = ready()
            owner, _ = reader(binding)
            journal = recipes.local / "operations" / (operation.operation_id + ".json")
            if catalog_id is None:
                open_recipe_catalog(
                    menus, journal, initial, before_action=ready, cancelled=cancelled
                )
                owner_after, catalog = reader(binding, catalog=True)
                final = _ready(menus.inspect(), binding.game_window_handle)
                if (
                    owner_after != owner
                    or final.owner != initial.owner
                    or catalog["root_address"] != final.root
                    or catalog["manager_address"] != final.manager
                    or catalog["menu_address"] != final.menu
                    or catalog["recipe_address"] != final.recipe
                    or catalog["list_address"] != final.recipe_list
                    or catalog["building"]["object_id"] != final.building
                    or catalog["vendor"]["object_id"] != final.vendor
                ):
                    raise VendorBatchStopped("recipe catalog owner changed")
                record = dict(
                    schema_version=1,
                    identity=list(store.identity),
                    owner=owner,
                    catalog_id=uuid.uuid4().hex,
                    snapshot=catalog,
                    menu_snapshot=final.encode().hex(),
                )
                _write(recipes.local / "catalog.json", record)
                recipes.activate(owner, catalog["building"], catalog["vendor"])
                return "Recipe list loaded. Choose a recipe and save it for random rolls."
            catalog = recipes.catalog(catalog_id)
            expected = Snapshot.decode(bytes.fromhex(catalog["menu_snapshot"]))
            matches = [
                row
                for row in catalog["snapshot"]["recipes"]
                if row["template"]["object_id"] == template
            ]
            if (
                catalog["owner"] != owner
                or initial.owner != expected.owner
                or initial.recipe != expected.recipe
                or initial.recipe_list != expected.recipe_list
                or len(matches) != 1
                or type(template) is not int
            ):
                raise VendorBatchStopped("selected recipe no longer belongs to this vendor list")
            prepare_recipe(
                menus, journal, initial, template, before_action=ready, cancelled=cancelled
            )
            _, _, prepared = validate_completed_menu(_read_record(journal, 256 * 1024))
            final = _ready(menus.inspect(), binding.game_window_handle)
            owner_after, _ = reader(binding)
            if (owner_after != owner or final.owner != initial.owner
                    or final.revision < prepared.revision
                    or replace(final, revision=0) != replace(prepared, revision=0)
                    or not final.random_recipe(template)):
                raise VendorBatchStopped("random recipe changed before saving")
            recipes.save(
                owner,
                catalog["snapshot"]["building"],
                catalog["snapshot"]["vendor"],
                RandomRecipeSpec(template, final.table),
                matches[0]["display_name"],
            )
            return "Random recipe saved. Start fills one batch of available slots."
        finally:
            menus.close()


def require_saved_owner(selection, binding, session, *, reader=read_context):
    owner, _ = reader(binding)
    receipt = session.inspect_random()
    snapshot = receipt.snapshot
    after, _ = reader(binding)
    if (
        receipt.outcome != Outcome.OBSERVED
        or receipt.flags & 6
        or receipt.window != binding.game_window_handle
        or owner != after
        or owner != selection["owner"]
        or snapshot.building != selection["building"]["object_id"]
        or snapshot.vendor != selection["vendor"]["object_id"]
        or not _owner(snapshot)[0]
    ):
        raise VendorBatchStopped("saved recipe belongs to another character or vendor")
    return dict(selection, admission_snapshot=snapshot.encode().hex())
