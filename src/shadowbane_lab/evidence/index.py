"""Disposable SQLite query index rebuilt from canonical evidence manifests."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from .codec import load_manifest
from .model import EvidenceError, EvidenceManifest

INDEX_SCHEMA_VERSION = 1


def rebuild_index(manifest_directory: str | Path, index_path: str | Path) -> int:
    source = Path(manifest_directory)
    if not source.is_dir():
        raise EvidenceError(f"manifest directory does not exist: {source}")
    destination = Path(index_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    count = 0
    try:
        connection = sqlite3.connect(temporary)
        try:
            _create_schema(connection)
            for path in sorted(source.rglob("*.json"), key=lambda item: item.as_posix().casefold()):
                try:
                    manifest = load_manifest(path)
                except EvidenceError as exc:
                    raise EvidenceError(f"cannot index manifest {path}: {exc}") from exc
                _insert_manifest(connection, manifest, path)
                count += 1
            connection.execute(f"PRAGMA user_version = {INDEX_SCHEMA_VERSION}")
            connection.commit()
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise EvidenceError("rebuilt evidence index failed integrity check")
        finally:
            connection.close()
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return count


def query_index(
    index_path: str | Path,
    *,
    artifact_kind: str | None = None,
    case_id: str | None = None,
    run_id: str | None = None,
    limit: int = 100,
) -> tuple[dict[str, object], ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
        raise ValueError("query limit must be in [1, 10000]")
    connection = sqlite3.connect(f"file:{Path(index_path).resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        clauses: list[str] = []
        values: list[object] = []
        if artifact_kind is not None:
            clauses.append("a.artifact_kind = ?")
            values.append(artifact_kind)
        if case_id is not None:
            clauses.append("m.case_id = ?")
            values.append(case_id)
        if run_id is not None:
            clauses.append("m.run_id = ?")
            values.append(run_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = connection.execute(
            "SELECT m.manifest_id, m.case_id, m.run_id, m.terminal_state, "
            "a.artifact_id, a.artifact_kind, a.logical_name, a.size_bytes "
            "FROM manifests m JOIN artifacts a ON a.manifest_id = m.manifest_id"
            + where
            + " ORDER BY m.created_at_utc DESC, a.artifact_id LIMIT ?",
            (*values, limit),
        ).fetchall()
        return tuple(dict(row) for row in rows)
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = FULL;
        CREATE TABLE manifests (
            manifest_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            fingerprint_id TEXT,
            case_id TEXT,
            experiment_id TEXT,
            run_id TEXT,
            terminal_state TEXT NOT NULL,
            source_path TEXT NOT NULL
        );
        CREATE TABLE artifacts (
            manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id),
            artifact_id TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            media_type TEXT NOT NULL,
            logical_name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            PRIMARY KEY (manifest_id, artifact_id)
        );
        CREATE INDEX artifacts_by_kind ON artifacts(artifact_kind);
        CREATE INDEX manifests_by_case ON manifests(case_id);
        CREATE INDEX manifests_by_run ON manifests(run_id);
        """
    )


def _insert_manifest(
    connection: sqlite3.Connection,
    manifest: EvidenceManifest,
    source_path: Path,
) -> None:
    connection.execute(
        "INSERT INTO manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            manifest.manifest_id,
            manifest.created_at_utc,
            manifest.fingerprint_id,
            manifest.case_id,
            manifest.experiment_id,
            manifest.run_id,
            manifest.terminal_state.value,
            str(source_path.resolve()),
        ),
    )
    connection.executemany(
        "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                manifest.manifest_id,
                descriptor.artifact_id,
                descriptor.artifact_kind.value,
                descriptor.media_type,
                descriptor.logical_name,
                descriptor.size_bytes,
            )
            for descriptor in manifest.artifacts
        ),
    )


__all__ = ["INDEX_SCHEMA_VERSION", "query_index", "rebuild_index"]
