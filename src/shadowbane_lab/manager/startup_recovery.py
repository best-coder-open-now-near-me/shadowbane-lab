"""Recover exact slot ownership after a manager-only process restart."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .manifest import ManagerManifest
from .model import ClientInstanceSnapshot, ClientRegistrySnapshot
from .worker import WorkerLedgerSnapshot


class RecoveryRegistry(Protocol):
    def inspect(self) -> ClientRegistrySnapshot: ...


class RecoveryLedger(Protocol):
    def inspect(self, client_id: str) -> WorkerLedgerSnapshot: ...


class RecoverySession(Protocol):
    def attach(self, client_id: str, *, instance_id: str) -> object: ...


class RecoveryWorkerController(Protocol):
    def ensure_started(
        self,
        client_id: str,
        client: ClientInstanceSnapshot,
    ) -> int | None: ...


@dataclass(frozen=True, slots=True)
class BindingRecoveryIssue:
    client_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class BindingRecoverySnapshot:
    recovered_client_ids: tuple[str, ...]
    issues: tuple[BindingRecoveryIssue, ...]


def recover_manager_bindings(
    manifest: ManagerManifest,
    registry: RecoveryRegistry,
    ledger: RecoveryLedger,
    session: RecoverySession,
    worker_controller: RecoveryWorkerController,
) -> BindingRecoverySnapshot:
    """Reattach only unambiguous one-to-one heartbeat and live-window identities."""

    if not isinstance(manifest, ManagerManifest):
        raise ValueError("manifest must be ManagerManifest")
    snapshot = registry.inspect()
    if not isinstance(snapshot, ClientRegistrySnapshot) or snapshot.node_id != manifest.node_id:
        raise RuntimeError("binding recovery registry returned an invalid node snapshot")
    clients_by_id = {client.instance_id: client for client in snapshot.clients}
    candidates: dict[str, str] = {}
    claim_counts: Counter[str] = Counter()
    issues: list[BindingRecoveryIssue] = []
    for config in manifest.clients:
        slot = ledger.inspect(config.client_id)
        if not isinstance(slot, WorkerLedgerSnapshot) or slot.client_id != config.client_id:
            raise RuntimeError("binding recovery ledger returned an invalid slot snapshot")
        if slot.issues:
            issues.append(
                BindingRecoveryIssue(
                    client_id=config.client_id,
                    detail="worker heartbeat records are invalid; automatic recovery skipped",
                )
            )
            continue
        current_instance_ids = {
            record.instance_id for record in slot.records if record.instance_id in clients_by_id
        }
        claim_counts.update(current_instance_ids)
        if len(current_instance_ids) == 1:
            candidates[config.client_id] = next(iter(current_instance_ids))
        elif len(current_instance_ids) > 1:
            issues.append(
                BindingRecoveryIssue(
                    client_id=config.client_id,
                    detail="multiple current clients have prior worker ownership records",
                )
            )

    recovered: list[str] = []
    for config in manifest.clients:
        instance_id = candidates.get(config.client_id)
        if instance_id is None:
            continue
        if claim_counts[instance_id] != 1:
            issues.append(
                BindingRecoveryIssue(
                    client_id=config.client_id,
                    detail="one current client is claimed by multiple prior slots",
                )
            )
            continue
        try:
            session.attach(config.client_id, instance_id=instance_id)
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(
                BindingRecoveryIssue(
                    client_id=config.client_id,
                    detail=f"exact lifecycle reattachment failed: {exc}",
                )
            )
            continue
        recovered.append(config.client_id)
        try:
            worker_controller.ensure_started(
                config.client_id,
                clients_by_id[instance_id],
            )
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(
                BindingRecoveryIssue(
                    client_id=config.client_id,
                    detail=f"worker restart after reattachment failed: {exc}",
                )
            )
    return BindingRecoverySnapshot(
        recovered_client_ids=tuple(recovered),
        issues=tuple(issues),
    )


__all__ = [
    "BindingRecoveryIssue",
    "BindingRecoverySnapshot",
    "recover_manager_bindings",
]
