import json
from dataclasses import replace

import pytest
from test_manager_operation import _permit

from shadowbane_lab.manager.operation import (
    WorkerOperationFormatError,
    WorkerOperationKind,
    WorkerPlayerAttackTarget,
    loads_worker_operation,
    new_worker_operation,
)


def target():
    return WorkerPlayerAttackTarget((42, 53), "Other Player", "Wonderbane", (7, 53))


def operation():
    return new_worker_operation(_permit(), WorkerOperationKind.PLAYER_ATTACK, "/attack Other",
                                player_target=target(), now=100)


def test_exact_target_roundtrips_and_changes_immutable_deduplication():
    first = operation()
    assert loads_worker_operation(json.dumps(first.to_dict())) == first
    changed = new_worker_operation(_permit(), first.kind, first.command, now=100,
                                  operation_id=first.operation_id,
                                  player_target=replace(target(), object_key=(43, 53)))
    assert changed.deduplication_id != first.deduplication_id


@pytest.mark.parametrize("change", [dict(object_key=(7, 53)), dict(object_key=(42, 37)),
                                   dict(local_key=(True, 53)), dict(name="Other\n"),
                                   dict(server=""), dict(object_key=(2**32, 53))])
def test_target_rejects_nonexact_identity(change):
    with pytest.raises(WorkerOperationFormatError):
        replace(target(), **change)


def test_missing_or_cross_kind_target_rejected_but_historical_envelopes_unchanged():
    with pytest.raises(WorkerOperationFormatError):
        replace(operation(), player_target=None)
    with pytest.raises(WorkerOperationFormatError):
        replace(operation(), kind=WorkerOperationKind.PVE)
    old = new_worker_operation(_permit(), WorkerOperationKind.PVE, "/pve", now=100)
    assert "player_target" not in old.to_dict()
    assert loads_worker_operation(json.dumps(old.to_dict())) == old
    malformed = old.to_dict() | {"player_target": target().to_dict()}
    with pytest.raises(WorkerOperationFormatError):
        loads_worker_operation(json.dumps(malformed))
    row = operation().to_dict()
    del row["player_target"]
    with pytest.raises(WorkerOperationFormatError):
        loads_worker_operation(json.dumps(row))
