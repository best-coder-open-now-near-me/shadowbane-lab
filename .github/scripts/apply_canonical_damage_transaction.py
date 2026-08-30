from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EFFECTS = ROOT / "src/shadowbane_lab/sim/effects.py"
SIM_INIT = ROOT / "src/shadowbane_lab/sim/__init__.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement target, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    path.write_text(
        text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:],
        encoding="utf-8",
    )


def patch_exports() -> None:
    replace_once(
        SIM_INIT,
        "from shadowbane_lab.sim.clock import ClockSnapshot, SimulationClock\n",
        "from shadowbane_lab.sim.clock import ClockSnapshot, SimulationClock\n"
        "from shadowbane_lab.sim.damage import DamageResolution, DamageTransaction\n",
    )
    replace_once(
        SIM_INIT,
        '    "DamageBreakpoint",\n    "DamageType",\n',
        '    "DamageBreakpoint",\n    "DamageResolution",\n    "DamageTransaction",\n'
        '    "DamageType",\n',
    )


def patch_effects() -> None:
    replace_once(
        EFFECTS,
        "from shadowbane_lab.sim.errors import SimulationConfigurationError\n",
        "from shadowbane_lab.sim.damage import DamageResolution, DamageTransaction\n"
        "from shadowbane_lab.sim.errors import SimulationConfigurationError\n",
    )
    replace_once(
        EFFECTS,
        '''        if isinstance(effect, DealDamage):
            before = subject.scalars.get("health", 0.0) if subject is not None else 0.0
            self._deal_damage(item, effect, subject, due_time, events)
            after = subject.scalars.get("health", 0.0) if subject is not None else before
            effective = max(0.0, before - after)
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if effective > 0.0 else EffectOutcomeKind.RESISTED,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                magnitude=effective,
            )
''',
        '''        if isinstance(effect, DealDamage):
            resolution = self._deal_damage(item, effect, subject, due_time, events)
            return EffectOutcome(
                (
                    EffectOutcomeKind.APPLIED
                    if resolution.effective > 0.0
                    else EffectOutcomeKind.RESISTED
                ),
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                magnitude=resolution.effective,
            )
''',
    )

    replace_between(
        EFFECTS,
        "    def _apply_weapon_damage(\n",
        "    def _matching_trigger_contexts(\n",
        '''    def _apply_weapon_damage(
        self,
        item: ScheduledItem,
        subject: EntityState,
        amount: float,
        damage_type: str,
        due_time: int,
        events: list[Event],
        *,
        extra_tags: tuple[str, ...] = (),
    ) -> float:
        actor = self._entity(item.actor_id)
        amount *= self._scalar_or_default(actor, "outgoing.damage.factor", 1.0)
        amount *= self._scalar_or_default(
            actor,
            "outgoing.weapon.damage.factor",
            1.0,
        )
        raw_resistance = subject.scalars.get(
            f"resistance.{damage_type}", subject.scalars.get("resistance.all", 0.0)
        )
        resistance_cap = subject.scalars.get(
            f"resistance_cap.{damage_type}", subject.scalars.get("resistance_cap", 0.75)
        )
        resistance_floor = subject.scalars.get(
            f"resistance_floor.{damage_type}",
            subject.scalars.get("resistance_floor", -1.0),
        )
        if resistance_cap < resistance_floor:
            raise SimulationConfigurationError("resistance cap is below resistance floor")
        resistance = max(resistance_floor, min(resistance_cap, raw_resistance))
        after_resistance = max(0.0, amount * (1.0 - resistance))
        try:
            breakpoint_damage_type = DamageType(damage_type)
        except ValueError:
            breakpoint_damage_type = None
        if breakpoint_damage_type is DamageType.UNKNOWN:
            breakpoint_damage_type = None
        resolution = self._commit_damage(
            item,
            subject,
            DamageTransaction(
                damage_type=damage_type,
                requested=amount,
                post_resistance=after_resistance,
                resistance_percent=resistance * 100.0,
                breakpoint_damage_type=breakpoint_damage_type,
                breakpoint_amount=(
                    after_resistance if breakpoint_damage_type is not None else 0.0
                ),
                tags=extra_tags,
            ),
            due_time,
            events,
        )
        return resolution.effective

    def _commit_damage(
        self,
        item: ScheduledItem,
        subject: EntityState,
        transaction: DamageTransaction,
        due_time: int,
        events: list[Event],
    ) -> DamageResolution:
        remaining, absorbed = self._consume_damage_absorbers(
            item,
            subject,
            transaction.damage_type,
            transaction.post_resistance,
            due_time,
            events,
        )
        before = subject.scalars.get("health", 0.0)
        after = max(0.0, before - remaining)
        subject.scalars["health"] = after
        resolution = DamageResolution(
            transaction=transaction,
            absorbed=absorbed,
            health_before=before,
            health_after=after,
        )
        event_tags = [f"damage.{transaction.damage_type}", *transaction.tags]
        if item.trigger_key is not None:
            event_tags.append(f"trigger.{item.trigger_key}")
        events.append(
            self._event(
                EventKind.DAMAGE_APPLIED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("requested", transaction.requested),
                    NamedScalar("mitigated", transaction.post_resistance),
                    NamedScalar("post_resistance", transaction.post_resistance),
                    NamedScalar("resistance", transaction.resistance_fraction),
                    NamedScalar("resistance_percent", transaction.resistance_percent),
                    NamedScalar("armor_piercing", transaction.armor_piercing),
                    NamedScalar("resisted", transaction.resisted),
                    NamedScalar("absorbed", resolution.absorbed),
                    NamedScalar("effective", resolution.effective),
                ),
                tags=tuple(dict.fromkeys(event_tags)),
            )
        )
        if (
            transaction.breakpoint_damage_type is not None
            and transaction.breakpoint_amount > 0.0
        ):
            self._accumulate_damage_breakpoints(
                item,
                subject,
                transaction.breakpoint_damage_type,
                transaction.breakpoint_amount,
                due_time,
                events,
            )
        if resolution.effective > 0.0:
            self._drop_travel_stance(item, subject, due_time, events, reason="damage")
            self._interrupt_actor(subject.entity_id, "damage", due_time, events)
        return resolution

    def _consume_damage_absorbers(
        self,
        item: ScheduledItem,
        subject: EntityState,
        damage_type: str,
        amount: float,
        due_time: int,
        events: list[Event],
    ) -> tuple[float, float]:
        remaining = amount
        absorbed_total = 0.0
        candidates = sorted(
            (
                (storage_key, active)
                for storage_key, active in subject.effects.items()
                if active.magnitude > 0.0
                and (
                    "damage.absorb.all" in active.tags
                    or f"damage.absorb.{damage_type}" in active.tags
                )
            ),
            key=lambda value: (value[1].expires_at_ms, value[0]),
        )
        for storage_key, active in candidates:
            if remaining <= 0.0:
                break
            absorbed = min(remaining, active.magnitude)
            if absorbed <= 0.0:
                continue
            active.magnitude -= absorbed
            remaining -= absorbed
            absorbed_total += absorbed
            events.append(
                self._event(
                    EventKind.ABSORBER_CONSUMED,
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=active.source_entity_id,
                    target_entity_id=subject.entity_id,
                    action_key=item.action_key,
                    scalars=(
                        NamedScalar("absorbed", absorbed),
                        NamedScalar("remaining", active.magnitude),
                    ),
                    tags=(
                        f"effect.{active.effect_key}",
                        f"damage.{damage_type}",
                    ),
                )
            )
            if active.magnitude <= 0.0 and subject.effects.get(storage_key) is active:
                subject.effects.pop(storage_key)
                events.append(
                    self._effect_removed_event(
                        subject,
                        active,
                        due_time,
                        item,
                        "reason.depleted",
                    )
                )
        return remaining, absorbed_total
''',
    )

    replace_between(
        EFFECTS,
        "    def _deal_damage(\n",
        "    def _accumulate_damage_breakpoints(\n",
        '''    def _deal_damage(
        self,
        item: ScheduledItem,
        effect: DealDamage,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> DamageResolution:
        if subject is None:
            raise SimulationConfigurationError("damage requires an entity subject")
        amount = self._resolve_amount(effect.amount)
        actor = self._entity(item.actor_id)
        amount *= self._scalar_or_default(actor, "outgoing.damage.factor", 1.0)
        factor_key = (
            "outgoing.proc.damage.factor"
            if effect.source_key is not None and effect.source_key.startswith("proc.")
            else (
                "outgoing.power.damage.factor"
                if self._action_has_tag(item.action_key, "power")
                else "outgoing.weapon.damage.factor"
            )
        )
        amount *= self._scalar_or_default(actor, factor_key, 1.0)
        mitigated = amount
        resistance = 0.0
        armor_piercing = 0.0
        if effect.uses_resistance:
            resistance = self._required_scalar(subject, f"resist.{effect.damage_type.value}")
            resistance += sum(
                modifier.amount
                for storage_key in sorted(subject.effects)
                for active in (subject.effects[storage_key],)
                for modifier in active.modifiers
                if isinstance(modifier, ResistanceAdjustment)
                and modifier.damage_type is effect.damage_type
            )
            armor_piercing = self._required_scalar(actor, "armor_piercing")
            protection_applies = f"protection.{effect.damage_type.value}" in subject.effective_tags
            protection_trains = 0
            if protection_applies:
                raw_trains = self._required_scalar(subject, "protection.trains")
                if raw_trains < 0 or not raw_trains.is_integer():
                    raise SimulationConfigurationError(
                        f"entity {subject.entity_id} protection.trains must be a "
                        "non-negative integer"
                    )
                protection_trains = int(raw_trains)
            resistance = effective_resistance(
                resistance,
                protection_trains=protection_trains,
                incoming_trains=effect.power_trains,
                protection_applies=protection_applies,
            )
            mitigated = resisted_amount(amount, resistance, armor_piercing)
            if f"immunity.damage.{effect.damage_type.value}" in subject.effective_tags:
                mitigated = 0.0
            if "state.sitting" in subject.effective_tags:
                mitigated *= 2.5
        return self._commit_damage(
            item,
            subject,
            DamageTransaction(
                damage_type=effect.damage_type.value,
                requested=amount,
                post_resistance=mitigated,
                resistance_percent=resistance,
                armor_piercing=armor_piercing,
                breakpoint_damage_type=effect.damage_type,
                breakpoint_amount=mitigated,
                tags=(
                    *((f"damage_source.{effect.source_key}",) if effect.source_key else ()),
                ),
            ),
            due_time,
            events,
        )
''',
    )


def main() -> None:
    patch_exports()
    patch_effects()


if __name__ == "__main__":
    main()
