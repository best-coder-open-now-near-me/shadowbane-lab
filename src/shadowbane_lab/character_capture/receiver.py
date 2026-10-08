"""Private report ingestion. Run behind the existing private HTTPS proxy."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from shadowbane_lab.evidence import verify_bundle

MAX_REPORT_BYTES = 140 * 1024 * 1024


def bounded_bundle(path):
    """Validate geometry before the shared verifier reads any uploaded member."""
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 64 or sum(i.file_size for i in entries) > MAX_REPORT_BYTES:
            raise ValueError("Report is too large.")
        if any(i.compress_type != ZIP_STORED or i.flag_bits & 1 for i in entries):
            raise ValueError("Report must use the recorder's uncompressed evidence format.")
        for name in ("bundle.json", "manifest.json"):
            if archive.getinfo(name).file_size > 1024 * 1024:
                raise ValueError("Report metadata is too large.")
    manifest = verify_bundle(path)
    if not manifest.run_id or not manifest.run_id.startswith("watch-"):
        raise ValueError("This is not a tester recording.")
    return manifest


class ReportReceiver:
    def __init__(self, root, config):
        self.root, self.config = Path(root).resolve(), Path(config).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.incoming = self.root / "incoming"
        self.incoming.mkdir(exist_ok=True)
        self.reports = self.root / "reports"
        self.reports.mkdir(exist_ok=True)
        with self.database() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reports(
                digest TEXT PRIMARY KEY, owner TEXT NOT NULL, received TEXT NOT NULL,
                size INTEGER NOT NULL, run_id TEXT NOT NULL)""")

    @contextmanager
    def database(self):
        db = sqlite3.connect(self.root / "reports.sqlite", timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def __call__(self, environ, start_response):
        status, result = self.handle(environ)
        raw = json.dumps(result, sort_keys=True).encode()
        start_response(
            status,
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(raw))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [raw]

    def handle(self, env):
        path = env.get("PATH_INFO", "")
        if path.startswith("/shadowbane-reports/"):
            path = path.removeprefix("/shadowbane-reports")
        if env.get("REQUEST_METHOD") == "GET" and path == "/health":
            return "200 OK", {"service": "shadowbane-reports", "version": 1}
        match = re.fullmatch(r"/v1/reports/([a-f0-9]{64})", path)
        if env.get("REQUEST_METHOD") != "POST" or not match:
            return "404 Not Found", {"error": "Unknown report endpoint."}
        try:
            config = json.loads(self.config.read_text(encoding="utf-8-sig"))
            bearer = env.get("HTTP_AUTHORIZATION", "")
            if not bearer.startswith("Bearer ") or len(bearer) > 256:
                return "401 Unauthorized", {"error": "Report connection is not authorized."}
            owner = hashlib.sha256(bearer[7:].encode()).hexdigest()
            accepted = config.get("reporter_token_sha256", [])
            if not any(hmac.compare_digest(owner, candidate) for candidate in accepted):
                return "401 Unauthorized", {"error": "Report connection is not authorized."}
            try:
                length = int(env.get("CONTENT_LENGTH", ""))
            except ValueError:
                return "411 Length Required", {"error": "Report length is required."}
            if not 0 < length <= MAX_REPORT_BYTES:
                return "413 Content Too Large", {"error": "Report exceeds the upload limit."}
            if env.get("CONTENT_TYPE") != "application/zip":
                return "415 Unsupported Media Type", {"error": "Expected a recorder report."}
            digest = match[1]
            with self.database() as db:
                existing = db.execute(
                    "SELECT owner,received,size,run_id FROM reports WHERE digest=?", (digest,)
                ).fetchone()
            if existing:
                if existing[0] != owner:
                    return "409 Conflict", {"error": "Report identifier already exists."}
                target = self.reports / (digest + ".zip")
                with target.open("rb") as stored:
                    if (
                        target.stat().st_size != existing[2]
                        or hashlib.file_digest(stored, "sha256").hexdigest() != digest
                    ):
                        raise ValueError("Stored report is unavailable.")
                return "200 OK", self.receipt(digest, *existing[1:])
            return self.receive(env["wsgi.input"], length, digest, owner, config)
        except Exception:
            # Never include token, posted contents or local paths in an HTTP response/log.
            return "503 Service Unavailable", {
                "error": "Report storage is unavailable. Retry later."
            }

    @staticmethod
    def receipt(digest, received, size, run_id):
        return {
            "schema_version": 1,
            "report_id": "report-" + digest,
            "sha256": digest,
            "received_at_utc": received,
            "bytes": size,
            "run_id": run_id,
        }

    def receive(self, stream, length, digest, owner, config):
        descriptor, temporary = tempfile.mkstemp(prefix="upload-", dir=self.incoming)
        path = Path(temporary)
        try:
            total, checksum = 0, hashlib.sha256()
            with os.fdopen(descriptor, "wb") as output:
                while total < length:
                    chunk = stream.read(min(1024 * 1024, length - total))
                    if not chunk:
                        return "400 Bad Request", {"error": "Report upload was interrupted."}
                    output.write(chunk)
                    checksum.update(chunk)
                    total += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if checksum.hexdigest() != digest:
                return "422 Unprocessable Content", {"error": "Report checksum did not match."}
            try:
                manifest = bounded_bundle(path)
            except Exception:
                return "422 Unprocessable Content", {"error": "Report verification failed."}
            with self.database() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT owner,received,size,run_id FROM reports WHERE digest=?", (digest,)
                ).fetchone()
                if existing:
                    if existing[0] != owner:
                        return "409 Conflict", {"error": "Report identifier already exists."}
                    return "200 OK", self.receipt(digest, *existing[1:])
                used = db.execute("SELECT COALESCE(SUM(size),0) FROM reports").fetchone()[0]
                quota = int(config.get("maximum_store_bytes", 10 * 1024**3))
                if used + length > quota:
                    return "507 Insufficient Storage", {"error": "Report inbox is full."}
                today = datetime.now(UTC).date().isoformat()
                count = db.execute(
                    "SELECT COUNT(*) FROM reports WHERE owner=? AND received>=?", (owner, today)
                ).fetchone()[0]
                if count >= int(config.get("maximum_daily_reports", 100)):
                    return "429 Too Many Requests", {"error": "Daily report limit reached."}
                target = self.reports / (digest + ".zip")
                # Publishing the digest-named immutable file before the index makes a
                # crash recoverable: retry verifies the orphan and inserts its index.
                if target.exists():
                    with target.open("rb") as stored:
                        if hashlib.file_digest(stored, "sha256").hexdigest() != digest:
                            raise ValueError("Stored report collision.")
                else:
                    os.replace(path, target)
                received = datetime.now(UTC).isoformat()
                db.execute(
                    "INSERT INTO reports VALUES(?,?,?,?,?)",
                    (digest, owner, received, length, manifest.run_id),
                )
            return "201 Created", self.receipt(digest, received, length, manifest.run_id)
        finally:
            path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    from waitress import serve

    serve(
        ReportReceiver(args.root, args.config),
        host="127.0.0.1",
        port=args.port,
        threads=4,
        connection_limit=16,
        channel_timeout=60,
        max_request_body_size=MAX_REPORT_BYTES,
        clear_untrusted_proxy_headers=True,
    )


if __name__ == "__main__":
    main()
