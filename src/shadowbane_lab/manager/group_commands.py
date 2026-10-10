"""Fresh native group commands owned by the existing exact worker.

The observer thread only reads and records intent. The worker's supervision
thread requests preemption and its existing operation/handoff path executes it.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from shadowbane_lab.record_store import publish_atomic_record

# A receive event must still be recent at admission; this is not an arrival or
# movement timeout. Native positions without recent receive evidence are unknown.
MAX_SOURCE_AGE_MS = 5_000
_COMMAND = re.compile(r"/(come)|/attack\s+([^\s\[\]]+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class GroupCommand:
    event_id: str
    generation: int
    tick_ms: int
    scene: int
    local: tuple[int, int]
    group_digest: str
    sender_key: tuple[int, int]
    sender_name: str
    kind: str
    argument: str | None = None


def parse_command(text):
    match = _COMMAND.fullmatch(text.strip())
    if match is None:
        return None
    return ("come", None) if match[1] else ("attack", match[2])


class GroupCommandPolicy:
    """One highest-generation intent; old history and uncertainty never replay."""

    def __init__(self, lifetime, *, persist):
        self.lifetime, self.persist = lifetime, persist
        self.seeded = False
        self.chat_floor = 0
        self.generation = 0
        self.update_generation = 0
        self.positions = {}
        self.context = None
        self.pending = None
        self.last_counters = None
        self.detail = "Waiting for fresh native group messages."

    def unavailable(self):
        self.seeded = False
        self.pending = None
        self.positions.clear()
        self.detail = "Native group command evidence unavailable."

    def ingest(self, messages, updates, current, *, allowed, now_ms):
        counters = (messages["sequence"], updates["sequence"])
        # Persist consumption BEFORE publishing any actionable command. A failed
        # write is not permission to execute and retry the same message later.
        if counters != self.last_counters:
            self.persist({"schema": 1, "process": self.lifetime,
                          "messages": counters[0], "updates": counters[1]})
            self.last_counters = counters
        digest = current["group_digest"]
        if self.context != (current["scene"], current["local"], digest):
            self.positions.clear()
            self.pending = None
            self.context = (current["scene"], current["local"], digest)
        reset = (not self.seeded or not allowed or messages["initial_history"]
                 or updates["initial_history"] or messages["gap"] or updates["gap"]
                 or messages["stopped"] or updates["stopped"])
        if reset:
            self.chat_floor = messages["sequence"]
            self.generation = max(self.generation, messages["sequence"])
            self.update_generation = max(self.update_generation, updates["sequence"])
            self.positions.clear()
            self.pending = None
            self.seeded = allowed and not (messages["stopped"] or updates["stopped"])
            self.detail = "Listening for new commands." if allowed else "Group commands paused."
            return
        for record in updates["records"]:
            if record["stage"] != 3 or record["processing_generation"] <= self.update_generation:
                continue
            self.update_generation = record["processing_generation"]
            if not self._qualified(record, current, now_ms):
                self.positions.clear()
                continue
            payload = record["payload"]
            if payload["kind"] not in (1, 2, 5):
                self.positions.clear()
                continue
            # Only positively refreshed keys gain timestamps; omitted rows do
            # not become current because another group member was updated.
            for row in payload["positions"]:
                self.positions[row["key"]] = (record["tick_ms"], row["xyz"])
        for record in messages["records"]:
            if record["stage"] != 3 or record["processing_generation"] <= self.generation:
                continue
            self.generation = record["processing_generation"]
            if record["decode_sequence"] <= self.chat_floor or not self._qualified(
                    record, current, now_ms):
                continue
            payload = record["payload"]
            parsed = parse_command(payload["text"])
            if parsed is None:
                continue
            sender = payload["sender_key"]
            matches = [key for key, name in current["members"].items()
                       if name.casefold() == payload["sender"].casefold()]
            if matches != [sender]:
                self.detail = "Command sender is not a unique current group member."
                continue
            event = hashlib.sha256(json.dumps(
                [self.lifetime, record["decode_sequence"], record["processing_generation"]]
            ).encode()).hexdigest()
            self.pending = GroupCommand(event, record["processing_generation"], record["tick_ms"],
                current["scene"], current["local"], digest, sender, payload["sender"], *parsed)
            self.detail = f"Fresh {parsed[0]} command from {payload['sender']}."
        if self.pending is not None and not self.valid(self.pending, current, now_ms):
            self.pending = None
            self.detail = "Command expired or group identity changed before admission."

    @staticmethod
    def _qualified(record, current, now_ms):
        payload = record["payload"]
        return (record["flags"] == 15 and payload is not None
                and record["scene_epoch"] == current["scene"]
                and record["local"] == current["local"]
                and payload["group_digest"] == current["group_digest"]
                and 0 <= now_ms - record["tick_ms"] <= MAX_SOURCE_AGE_MS)

    @staticmethod
    def valid(command, current, now_ms):
        return (0 <= now_ms - command.tick_ms <= MAX_SOURCE_AGE_MS
                and (command.scene, command.local, command.group_digest)
                == (current["scene"], current["local"], current["group_digest"])
                and current["members"].get(command.sender_key, "").casefold()
                == command.sender_name.casefold())

    def destination(self, command, current, now_ms, *, positions=None):
        if not self.valid(command, current, now_ms):
            raise ValueError("group command identity or freshness changed")
        loaded = current.get("positions", {}).get(command.sender_key)
        if loaded is not None:
            return loaded
        stamped = (self.positions if positions is None else positions).get(command.sender_key)
        if stamped is None or not 0 <= now_ms - stamped[0] <= MAX_SOURCE_AGE_MS:
            raise ValueError("commanding member has no fresh native position")
        x, _altitude, z = stamped[1]
        return x, -z


class GroupCommandService:
    """Passive observation isolated from the worker's lease-maintenance thread."""

    def __init__(self, source, *, allowed, record_path, status_path=None, owner=None, interval=.25):
        self.source, self.allowed, self.interval = source, allowed, interval
        self.path = Path(record_path)
        self.status_path = None if status_path is None else Path(status_path)
        self.owner = owner
        self.enabled = False
        self.last_request = None
        self.policy = GroupCommandPolicy(source.lifetime, persist=self._persist)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.current = None
        self.now_ms = 0
        self.taken = None
        self.attack = None
        self.pending_value = None
        self.positions = {}
        self.seeded = False

    def _persist(self, record):
        publish_atomic_record(self.path, json.dumps(record, sort_keys=True).encode(),
                              temporary_label="group-consumption")

    def start(self):
        if self.thread is not None:
            raise RuntimeError("group observer already started")
        self.thread = threading.Thread(
            target=self._run, name="shadowbane-group-observer", daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while not self.stop.is_set():
                try:
                    # Ledger reconciliation may block; sample native evidence after it.
                    allowed = self.allowed()
                    messages, updates, current, now_ms = self.source.read()
                    enabled = current.get("enabled", False)
                    allowed = allowed and enabled
                    self.policy.ingest(messages, updates, current, allowed=allowed, now_ms=now_ms)
                    candidate = self.policy.pending
                    with self.lock:
                        self.enabled = enabled
                        self.current, self.now_ms = current, now_ms
                        self.positions = dict(self.policy.positions)
                        self.seeded = self.policy.seeded
                        self.pending_value = None if candidate == self.taken else candidate
                    if (candidate is not None and candidate.kind == "attack"
                            and candidate != self.taken):
                        try:
                            target = self.source.attack_target(candidate.argument)
                        except (OSError, RuntimeError, ValueError) as exc:
                            # A missing/protected named target is a consumed refusal,
                            # not a failure of the native group listener. Never retry
                            # this message against a later replacement target.
                            with self.lock:
                                self.taken = candidate
                                self.pending_value = None
                                self.attack = None
                            self.note(candidate, "withheld", str(exc)[:200])
                        else:
                            with self.lock:
                                if self.pending_value == candidate:
                                    self.attack = (candidate, target)
                    self._publish_status()
                except Exception:
                    self.policy.unavailable()
                    with self.lock:
                        self.pending_value = None
                        self.current = None
                        self.positions = {}
                        self.seeded = False
                    self._publish_status()
                self.stop.wait(self.interval)
        finally:
            self.source.close()

    def record_admission(self, command, operation):
        """Keep the exact native receive linkage beside the immutable operation.

        This records a requested admission, not execution or cleanup success;
        those remain the operation ledger's correlated receipts.
        """
        value = {"schema_version": 1, "owner": self.owner,
                 "process": self.policy.lifetime, "command": asdict(command),
                 "operation": operation.to_dict(), "recorded_at": time.time()}
        publish_atomic_record(self.path.with_name(f"admission-{command.event_id}.json"),
                              json.dumps(value, sort_keys=True).encode(),
                              temporary_label="group-admission")

    def note(self, command, state, detail=None):
        with self.lock:
            if command.kind == "attack":
                detail = f"Target: {command.argument}. " + (detail or "")
            self.last_request = {"command": command.kind, "sender": command.sender_name,
                                 "state": state, "detail": detail}

    def _publish_status(self):
        if self.status_path is None:
            return
        with self.lock:
            available = self.current is not None and bool(self.current["members"])
            state = ("unavailable" if not available else "disabled" if not self.enabled
                     else "listening" if self.seeded else "paused")
            value = {"schema_version": 1, "owner": self.owner, "observed_at": time.time(),
                     "enabled": self.enabled, "state": state, "current": available,
                     "detail": ("Not in a native group." if self.current is not None
                                and not self.current["members"] else self.policy.detail),
                     "last_request": self.last_request}
        try:
            publish_atomic_record(self.status_path, json.dumps(value).encode(),
                                  temporary_label="group-status")
        except (OSError, RuntimeError, ValueError):
            pass  # Reporting never changes command authority.

    def pending(self):
        from shadowbane_lab.client_extension.tracking_publication import tick_ms
        with self.lock:
            command, now = self.pending_value, tick_ms()
            if command is None:
                return None
            if (not self.enabled or not self.seeded or self.current is None
                    or not self.policy.valid(command, self.current, now)):
                self.pending_value = None
                self.taken = command
                return None
            if not 0 <= now - self.now_ms <= 500:
                return None  # Wait for a fresh observation within the receive deadline.
            if command.kind == "attack":
                return command if self.attack is not None and self.attack[0] == command else None
            try:
                self.policy.destination(command, self.current, now, positions=self.positions)
            except ValueError:
                self.pending_value = None
                return None
            return command

    def permits(self, command):
        """Refresh group/character permission, not a new receive-event lifetime."""
        from shadowbane_lab.client_extension.tracking_publication import tick_ms
        with self.lock:
            current = self.current
            return bool(self.enabled and current is not None and self.seeded
                and 0 <= tick_ms() - self.now_ms <= 500
                and (command.scene, command.local, command.group_digest)
                == (current["scene"], current["local"], current["group_digest"])
                and current["members"].get(command.sender_key, "").casefold()
                == command.sender_name.casefold())

    def claim(self, command):
        """Consume once before requesting an operation; no retry after ambiguity."""
        from shadowbane_lab.client_extension.tracking_publication import tick_ms
        with self.lock:
            if command != self.pending_value or command == self.taken:
                return None
            now = tick_ms()
            if (not self.enabled or not self.seeded or self.current is None
                    or not self.policy.valid(command, self.current, now)):
                self.pending_value = None
                self.taken = command
                raise ValueError(
                    "group command expired or permission changed before admission "
                    f"(command age {now - command.tick_ms} ms, "
                    f"observation age {now - self.now_ms} ms)")
            if not 0 <= now - self.now_ms <= 500:
                # No operation was requested. Keep the same received intent until
                # the observer refreshes, without extending its five-second deadline.
                self.last_request = {"command": command.kind, "sender": command.sender_name,
                    "state": "waiting", "detail": "Waiting for fresh native group evidence "
                    f"(observation age {now - self.now_ms} ms)."}
                return None
            self.pending_value = None
            self.taken = command
            destination = (self.policy.destination(
                command, self.current, now, positions=self.positions)
                if command.kind == "come" else None)
            target = None
            if command.kind == "attack":
                if self.attack is None or self.attack[0] != command:
                    raise ValueError("exact command target is unavailable")
                target = self.attack[1]
            return destination, target

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)


def create_worker_group_commands(binding, ledger, publisher, process, *, node_id):
    from .group_command_source import NativeGroupCommandSource
    gate = publisher.dispatch_gate()
    def allowed():
        control = ledger.inspect_preparation_control(binding.client_id, binding.instance_id)
        return not gate.is_set() and (control is None or control.enabled)
    owner = [node_id, binding.client_id, binding.instance_id, publisher.worker_id,
             process.process_id, process.process_started_at_100ns]
    directory = ledger.root / node_id / binding.client_id / "group-commands"
    directory.mkdir(parents=True, exist_ok=True)
    return GroupCommandService(NativeGroupCommandSource(binding), allowed=allowed,
        record_path=directory / f"{publisher.worker_id}-consumption.json",
        status_path=directory / f"{publisher.worker_id}-status.json", owner=owner)
