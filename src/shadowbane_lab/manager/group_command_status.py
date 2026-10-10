"""Passive group-command status, correlated with the current exact worker."""
import json
import time

from shadowbane_lab.record_store import read_record_bytes


def inspect_status(ledger, worker, binding, *, now=None):
    result = {"enabled": False, "state": "unavailable", "current": False,
              "detail": None, "last_request": None}
    heartbeat = worker.heartbeat
    if heartbeat is None or binding is None or worker.state.value != "healthy":
        return result
    path = (ledger.root / heartbeat.node_id / heartbeat.client_id / "group-commands"
            / f"{heartbeat.worker_id}-status.json")
    try:
        if path.is_symlink():
            return result
        value = json.loads(read_record_bytes(path, 8192))
        expected = [heartbeat.node_id, heartbeat.client_id, heartbeat.instance_id,
                    heartbeat.worker_id, heartbeat.process_id, heartbeat.process_started_at_100ns]
        now = time.time() if now is None else now
        if (value["schema_version"] != 1 or value["owner"] != expected
                or heartbeat.instance_id != binding.instance_id
                or type(value["enabled"]) is not bool or type(value["current"]) is not bool
                or value["state"] not in {"unavailable", "disabled", "listening", "paused"}
                or not 0 <= now - value["observed_at"] <= 3):
            return result
        return {k: value[k] for k in result}
    except (OSError, ValueError, KeyError, TypeError):
        return result
