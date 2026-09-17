"""Durable guard spending intents; unresolved attempts block later spending."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from shadowbane_lab.record_store import (
    exclusive_record_lock,
    publish_atomic_record,
    read_record_bytes,
)

from .guard_upgrade_wire import IN_FLIGHT, UNRESOLVED, Command, Outcome, Receipt, Verb


class GuardSpendingStopped(RuntimeError):
    pass


def _request(value: str) -> str:
    if not isinstance(value, str) or str(uuid.UUID(value)) != value or not uuid.UUID(value).int:
        raise ValueError("canonical nonzero spending request is required")
    return value


def _write(path: Path, record: dict) -> None:
    publish_atomic_record(
        path,
        (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"),
        temporary_label="guard-spending",
    )


def _read(path: Path) -> dict:
    raw = read_record_bytes(path, 8192)
    if len(raw) > 8192:
        raise GuardSpendingStopped("guard spending record exceeds its size bound")
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise GuardSpendingStopped("invalid guard spending record")
    return record


def _confirmed(command: Command, receipt: Receipt) -> bool:
    before, after = command.expected, receipt.snapshot
    a, b = before.navigation, after.navigation
    same = (
        a.scene == b.scene
        and a.root == b.root
        and a.manager == b.manager
        and a.building_hud == b.building_hud
        and a.vendor_hud == b.vendor_hud
        and a.selected_entry == b.selected_entry
        and (a.building_id, a.building_type, a.vendor_id, a.vendor_type)
        == (b.building_id, b.building_type, b.vendor_id, b.vendor_type)
        and before.upgrade_control == after.upgrade_control
        and before.progress_control == after.progress_control
    )
    return bool(
        same
        and receipt.outcome == Outcome.OBSERVED
        and receipt.transition_request == command.request_key
        and not receipt.flags & (IN_FLIGHT | UNRESOLVED)
        and after.funds == before.funds - before.cost
        and (
            (after.rank == before.rank and after.upgrading and after.control_flags & 4)
            or after.rank == before.rank + 1
        )
    )


class GuardUpgradeJournal:
    """One ledger per manager client instance, retained across host/client restarts.

    The caller supplies that instance's local directory. Historical requests are
    never replaced or retried. Only a correlated native observation can finish a
    submitted action; new process/character ownership cannot clear uncertainty.
    """

    def __init__(self, root: Path):
        root = Path(root).resolve()
        native = str(root)
        if os.name == "nt" and native.startswith("\\\\?\\"):
            native = native[4:]
        if native.startswith("\\\\") or native.upper().startswith("UNC\\"):
            raise ValueError("guard spending records require local storage")
        self.root = root / "guard-spending"
        self.active = self.root / "active.json"
        self.lock = self.root / "journal.lock"

    def _path(self, key: str) -> Path:
        return self.root / "requests" / (uuid.UUID(_request(key)).hex + ".json")

    def _record(self, key: str) -> tuple[dict, Command]:
        record = _read(self._path(key))
        if (
            set(record)
            != {
                "schema_version",
                "request_key",
                "process_id",
                "creation",
                "command",
                "submission",
                "completion",
                "unresolved",
            }
            or type(record["schema_version"]) is not int
            or record["schema_version"] != 1
            or type(record["unresolved"]) is not bool
            or record["request_key"] != key
            or type(record["process_id"]) is not int
            or not 0 < record["process_id"] < 2**32
            or type(record["creation"]) is not int
            or not 0 < record["creation"] < 2**64
        ):
            raise GuardSpendingStopped("invalid guard spending identity")
        command = Command.decode(bytes.fromhex(record["command"]), Verb.UPGRADE)
        if command.request_key != key:
            raise GuardSpendingStopped("guard spending command identity mismatch")
        submission = record["submission"]
        if submission is not None:
            submitted = Receipt.decode(bytes.fromhex(submission))
            if (
                submitted.request_key != key
                or submitted.host != command.host
                or submitted.window != command.window
            ):
                raise GuardSpendingStopped("guard spending submission mismatch")
        if record["completion"] is not None:
            if record["unresolved"]:
                raise GuardSpendingStopped("unresolved guard spend cannot be completed")
            if submission is None:
                raise GuardSpendingStopped("guard completion has no submission")
            completed = Receipt.decode(bytes.fromhex(record["completion"]))
            if (
                completed.host != command.host
                or completed.window != command.window
                or submitted.outcome != Outcome.SUBMITTED
                or not _confirmed(command, completed)
            ):
                raise GuardSpendingStopped("guard completion is not correlated")
        return record, command

    def _pending(self) -> tuple[dict, Command] | None:
        if not self.active.exists():
            requests = self.root / "requests"
            if requests.exists() and any(requests.iterdir()):
                raise GuardSpendingStopped("Guard spending pointer is missing; review is required.")
            return None
        pointer = _read(self.active)
        if set(pointer) != {"request_key"}:
            raise GuardSpendingStopped("invalid active spending pointer")
        key = pointer["request_key"]
        if key is None:
            return None
        record, command = self._record(_request(key))
        if record["unresolved"]:
            return record, command
        terminal = record["completion"] is not None
        if record["submission"] is not None:
            receipt = Receipt.decode(bytes.fromhex(record["submission"]))
            terminal |= receipt.outcome in (
                Outcome.STALE,
                Outcome.UNAVAILABLE,
                Outcome.INVALID,
                Outcome.EXHAUSTED,
            )
            # A rejection carrying unresolved/pending state cannot release spending.
            terminal &= (
                not receipt.flags & (IN_FLIGHT | UNRESOLVED) or record["completion"] is not None
            )
        if terminal:
            _write(self.active, {"request_key": None})
            return None
        return record, command

    def submit(self, identity, command: Command, dispatch) -> Receipt:
        # Encode before creating any files, and retain the exact host lease too.
        encoded = command.encode(Verb.UPGRADE)
        _request(command.request_key)
        if (
            type(identity.process_id) is not int
            or not 0 < identity.process_id < 2**32
            or type(identity.creation_filetime_utc) is not int
            or not 0 < identity.creation_filetime_utc < 2**64
        ):
            raise ValueError("exact game process lifetime is required")
        with exclusive_record_lock(self.lock):
            if self._pending() is not None:
                raise GuardSpendingStopped(
                    "An earlier guard spend is unresolved; no new action sent."
                )
            path = self._path(command.request_key)
            if path.exists():
                raise GuardSpendingStopped("This guard spend was already attempted; no retry sent.")
            record = {
                "schema_version": 1,
                "request_key": command.request_key,
                "process_id": identity.process_id,
                "creation": identity.creation_filetime_utc,
                "command": encoded.hex(),
                "submission": None,
                "completion": None,
                "unresolved": False,
            }
            _write(path, record)
            _write(self.active, {"request_key": command.request_key})
            # Every exception from here leaves the durable intent active.
            receipt = dispatch()
            receipt.encode()
            if (
                receipt.request_key != command.request_key
                or receipt.host != command.host
                or receipt.window != command.window
            ):
                raise GuardSpendingStopped("Guard submission receipt does not match its intent.")
            record["submission"] = receipt.encode().hex()
            record["unresolved"] = bool(receipt.flags & UNRESOLVED)
            _write(path, record)
            self._pending()
            return receipt

    def observe(self, identity, receipt: Receipt) -> None:
        receipt.encode()
        with exclusive_record_lock(self.lock):
            pending = self._pending()
            if pending is None:
                return
            record, command = pending
            if record["unresolved"]:
                return
            if (
                identity.process_id != record["process_id"]
                or identity.creation_filetime_utc != record["creation"]
                or receipt.host != command.host
                or receipt.window != command.window
            ):
                return
            if receipt.flags & UNRESOLVED:
                record["unresolved"] = True
                _write(self._path(command.request_key), record)
                return
            if record["submission"] is None:
                return  # Lost submission reply is retained for review, never inferred.
            submitted = Receipt.decode(bytes.fromhex(record["submission"]))
            if submitted.outcome != Outcome.SUBMITTED or not _confirmed(command, receipt):
                return
            record["completion"] = receipt.encode().hex()
            _write(self._path(command.request_key), record)
            _write(self.active, {"request_key": None})
