"""Read-only character ownership, independent of transient movement epochs."""
from dataclasses import asdict

from shadowbane_lab.client_observation.native_character_config import NativeCharacterConfigReader

from .guard_funding_cycle import GuardFundingCycleStopped
from .vendor_discovery import _memory


def read_guard_owner(binding):
    memory = _memory(binding)
    try:
        return asdict(NativeCharacterConfigReader(memory).observe())
    finally:
        memory.close()


def require_owner(expected, observed):
    if (not isinstance(expected, dict)
            or set(expected) != {"player_pointer", "character_name", "server_name"}
            or type(expected["player_pointer"]) is not int or expected["player_pointer"] <= 0
            or any(not isinstance(expected[k], str) or not expected[k]
                   for k in ("character_name", "server_name"))
            or expected != observed):
        raise GuardFundingCycleStopped("The guard job character changed; no action sent.")
