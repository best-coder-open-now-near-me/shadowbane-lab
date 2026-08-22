from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from typing import TypeAlias


class TargetMode(str, Enum):
    ENEMY = "enemy"
    SELF = "self"


class ScaleStat(str, Enum):
    NONE = "none"
    POWER = "power"
    CONTROL = "control"
    SUSTAIN = "sustain"
    MOBILITY = "mobility"
    VITALITY = "vitality"


class StatusKind(str, Enum):
    STUN = "stun"
    SILENCE = "silence"
    SNARE = "snare"
    WARD = "ward"
    BURN = "burn"
    HEALING_REDUCTION = "healing_reduction"


class RepositionMode(str, Enum):
    TOWARD_TARGET = "toward_target"
    AWAY_FROM_TARGET = "away_from_target"


class Recipient(str, Enum):
    ACTOR = "actor"
    TARGET = "target"


@dataclass(frozen=True, slots=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    @property
    def length(self) -> float:
        return hypot(self.x, self.y)

    def normalized(self) -> Vec2:
        magnitude = self.length
        if magnitude <= 1e-12:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / magnitude, self.y / magnitude)


ZERO_VEC2 = Vec2(0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Formula:
    base: float
    scale_stat: ScaleStat = ScaleStat.NONE
    coefficient: float = 0.0

    def evaluate(self, stats: BuildStats) -> float:
        if self.scale_stat is ScaleStat.NONE:
            return self.base
        return self.base + self.coefficient * getattr(stats, self.scale_stat.value)


@dataclass(frozen=True, slots=True)
class DealDamage:
    amount: Formula
    damage_type: str
    recipient: Recipient = Recipient.TARGET


@dataclass(frozen=True, slots=True)
class RestoreHealth:
    amount: Formula
    recipient: Recipient = Recipient.ACTOR


@dataclass(frozen=True, slots=True)
class ModifyResource:
    resource: str
    amount: Formula
    recipient: Recipient = Recipient.TARGET


@dataclass(frozen=True, slots=True)
class ApplyStatus:
    status: StatusKind
    duration: Formula
    magnitude: Formula = Formula(0.0)
    recipient: Recipient = Recipient.TARGET
    tick_damage: Formula | None = None
    tick_interval: float = 1.0
    damage_type: str = "arcane"


@dataclass(frozen=True, slots=True)
class Reposition:
    distance: Formula
    mode: RepositionMode
    recipient: Recipient = Recipient.ACTOR


Primitive: TypeAlias = DealDamage | RestoreHealth | ModifyResource | ApplyStatus | Reposition


@dataclass(frozen=True, slots=True)
class ActionSpec:
    id: str
    name: str
    target_mode: TargetMode
    range: float
    cast_time: float
    cooldown: float
    mana_cost: float = 0.0
    stamina_cost: float = 0.0
    requires_hit: bool = False
    tags: frozenset[str] = frozenset()
    effects: tuple[Primitive, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class BuildStats:
    name: str
    max_health: float
    max_mana: float
    max_stamina: float
    health_regen: float
    mana_regen: float
    stamina_regen: float
    move_speed: float
    accuracy: float
    evasion: float
    physical_resistance: float
    arcane_resistance: float
    fire_resistance: float
    power: float
    control: float
    sustain: float
    mobility: float
    vitality: float
    action_ids: tuple[str, ...]

    def resistance(self, damage_type: str) -> float:
        return {
            "physical": self.physical_resistance,
            "arcane": self.arcane_resistance,
            "fire": self.fire_resistance,
        }.get(damage_type, 0.0)


@dataclass(frozen=True, slots=True)
class PolicyTuning:
    aggression: float = 1.0
    sustain_bias: float = 1.0
    control_bias: float = 1.0
    defense_bias: float = 1.0
    resource_conservation: float = 0.5
    preferred_range: float = 5.0
    finisher_bias: float = 1.0


@dataclass(slots=True)
class ActiveStatus:
    kind: StatusKind
    source_index: int
    remaining: float
    magnitude: float
    tick_damage: float = 0.0
    tick_interval: float = 1.0
    time_to_tick: float = 1.0
    damage_type: str = "arcane"


@dataclass(slots=True)
class PendingAction:
    action_id: str
    target_index: int
    remaining: float


@dataclass(slots=True)
class CombatMetrics:
    damage_dealt: float = 0.0
    damage_received: float = 0.0
    healing_done: float = 0.0
    control_seconds_applied: float = 0.0
    resource_spent: float = 0.0
    invalid_actions: int = 0
    actions_started: int = 0
    distance_sum: float = 0.0
    distance_samples: int = 0
    actions_by_tag: dict[str, int] = field(default_factory=dict)

    @property
    def mean_distance(self) -> float:
        if self.distance_samples == 0:
            return 0.0
        return self.distance_sum / self.distance_samples

    @property
    def control_action_rate(self) -> float:
        if self.actions_started == 0:
            return 0.0
        return self.actions_by_tag.get("control", 0) / self.actions_started


@dataclass(slots=True)
class CombatantState:
    index: int
    team: int
    stats: BuildStats
    tuning: PolicyTuning
    position: Vec2
    health: float
    mana: float
    stamina: float
    cooldowns: dict[str, float] = field(default_factory=dict)
    statuses: dict[StatusKind, ActiveStatus] = field(default_factory=dict)
    pending_action: PendingAction | None = None
    movement_intent: Vec2 = ZERO_VEC2
    alive: bool = True
    metrics: CombatMetrics = field(default_factory=CombatMetrics)

    @classmethod
    def from_build(
        cls,
        *,
        index: int,
        team: int,
        stats: BuildStats,
        tuning: PolicyTuning,
        position: Vec2,
    ) -> CombatantState:
        return cls(
            index=index,
            team=team,
            stats=stats,
            tuning=tuning,
            position=position,
            health=stats.max_health,
            mana=stats.max_mana,
            stamina=stats.max_stamina,
        )

    def has_status(self, kind: StatusKind) -> bool:
        status = self.statuses.get(kind)
        return status is not None and status.remaining > 0.0

    @property
    def health_fraction(self) -> float:
        return max(0.0, self.health) / self.stats.max_health

    @property
    def mana_fraction(self) -> float:
        return max(0.0, self.mana) / self.stats.max_mana

    @property
    def stamina_fraction(self) -> float:
        return max(0.0, self.stamina) / self.stats.max_stamina


@dataclass(frozen=True, slots=True)
class Decision:
    target_index: int | None
    action_id: str | None
    movement: Vec2 = ZERO_VEC2


@dataclass(frozen=True, slots=True)
class CombatEvent:
    time: float
    kind: str
    actor_index: int | None
    target_index: int | None
    amount: float = 0.0
    detail: str = ""
