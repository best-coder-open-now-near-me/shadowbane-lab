"""Durable buff intent; all eligibility and effect coverage come from native publication."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .preparation import PreparationAction, PreparationGroup


class CoverageKind(StrEnum):
    ALL_DESCRIPTORS = "all_descriptors"
    TRANSFORM_MARKER = "transform_marker"


@dataclass(frozen=True, slots=True)
class BuffAction:
    action: PreparationAction
    coverage_power_id: int
    coverage_kind: CoverageKind = CoverageKind.ALL_DESCRIPTORS

    def __post_init__(self):
        if (not isinstance(self.action, PreparationAction)
                or type(self.coverage_power_id) is not int
                or not 0 < self.coverage_power_id < 2**32
                or not isinstance(self.coverage_kind, CoverageKind)):
            raise ValueError("buff action requires typed native selectors")
        if self.action.power_id is not None and self.coverage_power_id != self.action.power_id:
            raise ValueError("learned power coverage must come from its own native definition")
        if (self.action.item_template is not None
                and self.coverage_kind is not CoverageKind.ALL_DESCRIPTORS):
            raise ValueError("item coverage requires its configured effect-source definition")

    def as_dict(self):
        return {"action_id": self.action.action_id, "power_id": self.action.power_id,
                "item_template": (None if self.action.item_template is None
                                  else list(self.action.item_template)),
                "coverage_power_id": self.coverage_power_id,
                "coverage_kind": self.coverage_kind.value}


@dataclass(frozen=True, slots=True)
class BuffGroup:
    group_id: str
    alternatives: tuple[BuffAction, ...]

    def __post_init__(self):
        if (type(self.alternatives) is not tuple
                or not all(isinstance(a, BuffAction) for a in self.alternatives)):
            raise ValueError("buff alternatives must be immutable typed intent")
        self.policy_group()

    def policy_group(self):
        return PreparationGroup(self.group_id, tuple(a.action for a in self.alternatives))

    def as_dict(self):
        return {"group_id": self.group_id, "alternatives": [a.as_dict() for a in self.alternatives]}


@dataclass(frozen=True, slots=True)
class BuffSettings:
    enabled: bool = False
    groups: tuple[BuffGroup, ...] = ()

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.groups) is not tuple
                or len(self.groups) > 32 or not all(isinstance(g, BuffGroup) for g in self.groups)
                or len({g.group_id for g in self.groups}) != len(self.groups)):
            raise ValueError("buff configuration requires distinct bounded groups")
        actions = [a.action.action_id for g in self.groups for a in g.alternatives]
        if len(actions) > 32 or len(set(actions)) != len(actions) or (self.enabled and not actions):
            raise ValueError("buff settings require unique bounded actions and enabled intent")

    def as_dict(self):
        return {"enabled": self.enabled, "groups": [g.as_dict() for g in self.groups]}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"enabled", "groups"}:
            raise ValueError("invalid buff settings fields")
        if type(value["groups"]) is not list or len(value["groups"]) > 32:
            raise ValueError("invalid buff group list")
        groups = []
        for group in value["groups"]:
            if (not isinstance(group, dict) or set(group) != {"group_id", "alternatives"}
                    or type(group["alternatives"]) is not list
                    or not 1 <= len(group["alternatives"]) <= 16):
                raise ValueError("invalid buff alternatives")
            actions = []
            for action in group["alternatives"]:
                if not isinstance(action, dict) or set(action) != {
                    "action_id", "power_id", "item_template", "coverage_power_id", "coverage_kind"
                }:
                    raise ValueError("invalid buff action fields")
                template = action["item_template"]
                if template is not None and (type(template) is not list or len(template) != 2):
                    raise ValueError("item template requires a two-word reference")
                actions.append(BuffAction(
                    PreparationAction(action["action_id"], action["power_id"],
                                      None if template is None else tuple(template)),
                    action["coverage_power_id"], CoverageKind(action["coverage_kind"])))
            groups.append(BuffGroup(group["group_id"], tuple(actions)))
        return cls(value["enabled"], tuple(groups))
