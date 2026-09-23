"""Assess native crafting results without granting command or disposal authority."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache

from shadowbane_lab.equipment.affix_reference import load_bundled_affix_reference
from shadowbane_lab.equipment.model import AffixPosition
from shadowbane_lab.equipment.rolling_policy import RollDisposition, evaluate_roll_tiers

# Qualified with native parent action IDs plus the kept items' inventory labels.
# Bind to the exact tested executable and recipe, not merely similar UI names.
_QUALIFIED_BUILD = "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"
_QUALIFIED_TEMPLATE = 26990
_NAMES = {
    "SUF-123": (AffixPosition.SUFFIX, "of Genius"),
    "SUF-143": (AffixPosition.SUFFIX, "of Cruelty"),
    "PRE-028": (AffixPosition.PREFIX, "Taripontor"),
}


def compact_affix_token(identifier: str) -> int:
    """Hash only canonical PRE/SUF definition IDs, including A-Z components.

    This narrow grammar avoids general string hashes and special power aliases.
    The compact encoding is source-pinned to Hasher.SBStringHash at server
    revision 7c3a3fb84c55c1efaa615f4ef2711173629a27c8 and corroborated by the
    native parent/component definition strings. It does not assign a tier.
    """
    if not isinstance(identifier, str) or not re.fullmatch(
        r"(?:PRE|SUF)-[0-9]{3}[A-Z]?", identifier
    ):
        raise ValueError("expected a canonical PRE/SUF definition identifier")
    chars = identifier.encode("ascii")
    component = chars[7] if len(chars) == 8 else 0
    value = chars[4] ^ (component << 3)
    for char, shift in ((chars[5], 4), (chars[6], 4), (chars[2], 5), (chars[1], 5)):
        value = (value << shift) ^ char
    return ((value << 5) ^ (((component ^ 0x5A0) // 4) ^ chars[0])) & 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class AssessedAffix:
    token: int
    identifier: str | None
    name: str | None
    tier: int | None


@dataclass(frozen=True, slots=True)
class RollAssessment:
    disposition: RollDisposition
    reason: str
    prefix: AssessedAffix
    suffix: AssessedAffix
    reference_edition: str
    command_admitted: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@lru_cache(maxsize=1)
def _reference():
    return load_bundled_affix_reference()


def _resolve(token: int, position: AffixPosition, *, qualified: bool) -> AssessedAffix:
    if token == 0:
        return AssessedAffix(0, None, None, 0)  # Only used after completion validation.
    if qualified:
        for identifier, (expected_position, name) in _NAMES.items():
            if position != expected_position or compact_affix_token(identifier) != token:
                continue
            matches = _reference().lookup(name, position=position)
            # Cross-equipment/tier ambiguity is unknown, never a low-tier exclusion.
            tiers = {entry.tier for entry in matches}
            tier = next(iter(tiers)) if len(tiers) == 1 else None
            return AssessedAffix(token, identifier, name, tier)
    return AssessedAffix(token, None, None, None)


def assess_native_crafting_roll(record: dict[str, object]) -> RollAssessment:
    """Interpret one native schema-2 server CONFIRM_PRODUCE, without sending input.

    Session freshness, vendor ownership, queue membership, budgets and inventory
    reconciliation are separate admission requirements. This pure assessment
    cannot establish them, including when its disposition is EXCLUDE.
    """
    if (
        record.get("schema_version") != 2
        or record.get("record_type") != "crafting_message"
        or record.get("direction") != "server_to_client"
    ):
        raise ValueError("expected a schema-2 native server crafting message")
    message = record.get("message")
    if not isinstance(message, dict) or message.get("action_id") != 8:
        raise ValueError("expected CONFIRM_PRODUCE")
    roll = message.get("roll")
    if not isinstance(roll, dict):
        raise ValueError("missing native production result")
    values = (
        message.get("prefix_token"), message.get("suffix_token"),
        message.get("error_code"), roll.get("template_id"), roll.get("seconds_remaining"),
        roll.get("in_progress"), roll.get("complete_flag"),
    )
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in values):
        raise ValueError("invalid native production result fields")
    prefix_token, suffix_token, error, template, seconds, progress, complete = values
    if progress not in (0, 1) or complete not in (0, 1):
        raise ValueError("invalid native completion flags")
    completed = error == 0 and progress == 0 and complete == 1 and seconds == 0
    qualified = (
        record.get("executable_sha256") == _QUALIFIED_BUILD
        and template == _QUALIFIED_TEMPLATE
    )
    if not completed:
        # Zero tokens while cooking are hidden, not evidence of absent affixes.
        prefix = AssessedAffix(prefix_token, None, None, None)
        suffix = AssessedAffix(suffix_token, None, None, None)
        return RollAssessment(
            RollDisposition.WAIT, "result_not_confirmed_complete",
            prefix, suffix, _reference().edition,
        )
    prefix = _resolve(prefix_token, AffixPosition.PREFIX, qualified=qualified)
    suffix = _resolve(suffix_token, AffixPosition.SUFFIX, qualified=qualified)
    disposition = evaluate_roll_tiers(prefix.tier, suffix.tier, completed=True)
    reason = (
        "unknown_affix_preserved" if prefix.tier is None or suffix.tier is None
        else "confirmed_low_tier" if disposition == RollDisposition.EXCLUDE
        else "no_excluded_tier"
    )
    return RollAssessment(disposition, reason, prefix, suffix, _reference().edition)
