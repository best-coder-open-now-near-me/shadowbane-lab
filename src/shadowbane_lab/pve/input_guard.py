"""Revalidate ordinary PvE object binding at the existing per-input boundary.

This is a read-only external-process check, not an atomic native admission: the
client can still change state between this last read and handling keyboard input.
The executor separately enforces exact foreground/process lifetime and stop state.
"""

from __future__ import annotations

from collections.abc import Callable

from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.pve.authority_snapshot import NativeCharacterPopulationSource
from shadowbane_lab.pve.model import PvETrackedTarget


class PvEInputGuardError(RuntimeError):
    """The ordinary input no longer belongs to the sampled native engagement."""


class NativePvEInputGuard:
    def __init__(
        self,
        population_reader: NativeCharacterPopulationSource,
        *,
        target: Callable[[], PvETrackedTarget | None],
        cleanup_pending: Callable[[], bool],
    ) -> None:
        if not isinstance(population_reader, NativeCharacterPopulationSource):
            raise ValueError("population_reader must expose native process identity and population")
        if not callable(target) or not callable(cleanup_pending):
            raise ValueError("input guard requires target and cleanup accessors")
        self._reader = population_reader
        self._target = target
        self._cleanup_pending = cleanup_pending
        self._process_id = population_reader.process_id
        if type(self._process_id) is not int or self._process_id <= 0:
            raise ValueError("input guard requires an exact native process ID")
        initial = self._observe()
        self._local_key = initial.local_player_object_key
        if self._local_key is None:
            raise PvEInputGuardError("native local actor identity unavailable")

    def _observe(self) -> NativeCharacterPopulationObservation:
        if self._reader.process_id != self._process_id:
            raise PvEInputGuardError("native population process changed")
        value = self._reader.observe()
        if self._reader.process_id != self._process_id:
            raise PvEInputGuardError("native population process changed during input check")
        if not isinstance(value, NativeCharacterPopulationObservation):
            raise PvEInputGuardError("native population observation unavailable")
        return value

    @staticmethod
    def _identity(target: PvETrackedTarget | None):
        if target is None:
            return None
        if not isinstance(target, PvETrackedTarget):
            raise PvEInputGuardError("input engagement identity unavailable")
        return target.token, target.object_key

    def require_current(self) -> None:
        if self._cleanup_pending():
            raise PvEInputGuardError("combat cleanup is pending")
        expected = self._identity(self._target())
        population = self._observe()
        if population.local_player_object_key != self._local_key:
            raise PvEInputGuardError("native local actor identity changed")
        if self._cleanup_pending() or self._identity(self._target()) != expected:
            raise PvEInputGuardError("engagement changed during input check")
        if expected is None:
            return  # Acquisition is intentionally allowed to change selection.
        token, key = expected
        if population.selected_target_token != token:
            raise PvEInputGuardError("selected target no longer matches the engagement")
        character = next(
            (
                value
                for value in population.characters
                if value.token == token and value.object_key == key
            ),
            None,
        )
        if (
            character is None
            or not character.attack_eligible
            or character.character_kind is not NativeCharacterKind.NPC
        ):
            raise PvEInputGuardError(
                "bound native target is missing, replaced, dead, protected, or not an NPC"
            )
