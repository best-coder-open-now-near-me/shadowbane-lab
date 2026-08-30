"""Closed Shadowbane combat vocabularies shared by sheets and simulator effects."""

from __future__ import annotations

from enum import StrEnum


class CombatStance(StrEnum):
    """Mutually exclusive character posture used by combat and travel actions."""

    NORMAL = "normal"
    OFFENSIVE = "offensive"
    DEFENSIVE = "defensive"
    PRECISE = "precise"
    TRAVEL = "travel"


class DamageType(StrEnum):
    """Resistance channel used by one damage application.

    ``UNKNOWN`` is reserved for unattributed observations and may not be used by a
    resisted effect. Source powers and delivery methods belong in event metadata,
    not in this mechanical channel.
    """

    SLASH = "slash"
    CRUSH = "crush"
    PIERCE = "pierce"
    MAGIC = "magic"
    BLEED = "bleed"
    POISON = "poison"
    MENTAL = "mental"
    HOLY = "holy"
    UNHOLY = "unholy"
    LIGHTNING = "lightning"
    FIRE = "fire"
    COLD = "cold"
    UNKNOWN = "unknown"


RESISTED_DAMAGE_TYPES = frozenset(item for item in DamageType if item is not DamageType.UNKNOWN)


class ResistanceType(StrEnum):
    """Closed mitigation channels exposed by a complete combat sheet.

    Damage channels deliberately mirror :class:`DamageType`; healing is a
    resistance channel but is not damage. Keeping this separate prevents a
    free-form scalar key from silently inventing a new combat mechanic.
    """

    SLASH = DamageType.SLASH.value
    CRUSH = DamageType.CRUSH.value
    PIERCE = DamageType.PIERCE.value
    MAGIC = DamageType.MAGIC.value
    BLEED = DamageType.BLEED.value
    POISON = DamageType.POISON.value
    MENTAL = DamageType.MENTAL.value
    HOLY = DamageType.HOLY.value
    UNHOLY = DamageType.UNHOLY.value
    LIGHTNING = DamageType.LIGHTNING.value
    FIRE = DamageType.FIRE.value
    COLD = DamageType.COLD.value
    HEALING = "healing"
