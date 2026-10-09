"""Persistent explicit preparation intent, separate from temporary native admission."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_WORKER = re.compile(r"worker-[0-9a-f]{32}\Z")
_OPERATION = re.compile(r"operation-[0-9a-f]{32}\Z")


@dataclass(frozen=True, slots=True)
class PreparationControl:
    node_id: str
    client_id: str
    instance_id: str
    revision: int
    enabled: bool
    worker_id: str | None
    worker_process_id: int | None
    worker_process_creation: int | None
    superseded_stops: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        for value in (self.node_id, self.client_id, self.instance_id):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError("preparation control requires exact client identity")
        if (type(self.schema_version) is not int or self.schema_version != 1
                or type(self.enabled) is not bool
                or type(self.revision) is not int or not 0 < self.revision < 2**63):
            raise ValueError("invalid preparation control state")
        absent_worker = (self.worker_id is None and self.worker_process_id is None
                         and self.worker_process_creation is None)
        if absent_worker and not self.enabled:
            pass  # Explicit Stop is valid even before a worker has started.
        elif not isinstance(self.worker_id, str) or not _WORKER.fullmatch(self.worker_id):
            raise ValueError("preparation control requires an exact worker")
        for value in (self.worker_process_id, self.worker_process_creation):
            if not (absent_worker and not self.enabled) and (type(value) is not int or value <= 0):
                raise ValueError("preparation control requires worker process lifetime")
        if (type(self.superseded_stops) is not tuple or len(self.superseded_stops) > 256
                or len(set(self.superseded_stops)) != len(self.superseded_stops)
                or any(not isinstance(value, str) or not _OPERATION.fullmatch(value)
                       for value in self.superseded_stops)):
            raise ValueError("invalid superseded preparation stop operations")

    def to_dict(self):
        result = asdict(self)
        result["superseded_stops"] = list(self.superseded_stops)
        return result

    @classmethod
    def loads(cls, source):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate preparation control field")
                result[key] = value
            return result
        value = json.loads(source, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("invalid preparation control fields")
        if type(value["superseded_stops"]) is not list:
            raise ValueError("invalid superseded preparation stops")
        return cls(**{**value, "superseded_stops": tuple(value["superseded_stops"])})
