"""Explicit, retryable report delivery; secrets stay outside source and report bundles."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit

from .receiver import MAX_REPORT_BYTES, bounded_bundle


def load_connection(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    url = urlsplit(value["url"])
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("The report connection must use a private HTTPS address.")
    token = value.get("token")
    if not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii():
        raise ValueError("Invalid report connection.")
    return value


def save_delivery(folder, payload):
    path = Path(folder) / "delivery.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def deliver(folder, connection, *, progress=lambda sent, total: None, connection_factory=None):
    folder = Path(folder)
    report = folder / "evidence.zip"
    manifest = bounded_bundle(report)
    size = report.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError("This report is too large to send.")
    with report.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    url = urlsplit(connection["url"])
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("Invalid HTTPS destination.")
    state = {"sha256": digest, "destination": connection["url"], "status": "sending"}
    save_delivery(folder, state)
    factory = connection_factory or (
        lambda: http.client.HTTPSConnection(
            url.hostname, url.port or 443, timeout=60, context=ssl.create_default_context()
        )
    )
    client = factory()
    try:
        endpoint = url.path.rstrip("/") + "/v1/reports/" + digest
        client.putrequest("POST", endpoint)
        client.putheader("Authorization", "Bearer " + connection["token"])
        client.putheader("Content-Type", "application/zip")
        client.putheader("Content-Length", str(size))
        client.endheaders()
        with report.open("rb") as stream:
            sent = 0
            while chunk := stream.read(1024 * 1024):
                client.send(chunk)
                sent += len(chunk)
                progress(sent, size)
        response = client.getresponse()
        raw = response.read(16385)
        if response.status not in (200, 201):
            raise RuntimeError(f"Server did not accept the report (HTTP {response.status}).")
        if len(raw) > 16384:
            raise RuntimeError("Invalid server receipt.")
        receipt = json.loads(raw)
        if (
            receipt.get("schema_version") != 1
            or receipt.get("sha256") != digest
            or receipt.get("bytes") != size
            or receipt.get("run_id") != manifest.run_id
            or receipt.get("report_id") != "report-" + digest
        ):
            raise RuntimeError("Server receipt did not match this report.")
        save_delivery(folder, {**state, "status": "sent", "receipt": receipt})
        return receipt
    except Exception:
        save_delivery(
            folder,
            {
                **state,
                "status": "ready",
                "message": "Not confirmed. The local report is safe to retry.",
            },
        )
        raise
    finally:
        client.close()


def list_reports(root):
    items = []
    for path in sorted(Path(root).glob("watch-*"), reverse=True):
        try:
            summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
            if not (path / "evidence.zip").is_file():
                continue
            delivery = (
                json.loads((path / "delivery.json").read_text(encoding="utf-8"))
                if (path / "delivery.json").is_file()
                else {}
            )
            items.append(
                {
                    "path": path,
                    "summary": summary,
                    "status": "Sent" if delivery.get("status") == "sent" else "Ready to send",
                }
            )
        except (OSError, ValueError):
            continue
    return sorted(items, key=lambda x: x["summary"].get("started_at_utc", ""), reverse=True)
