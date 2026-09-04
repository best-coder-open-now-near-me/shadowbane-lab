"""Build provenance and the on-disk image of an actually loaded extension."""

import hashlib
import re
from pathlib import Path

from shadowbane_lab.character_capture.memory import WindowsProcessMemory
from shadowbane_lab.graphics_lab.control import target_process_is_alive

EXTENSION_NAME = re.compile(r"wonderbane-extension(?:-[0-9][0-9.]*)?\.dll", re.IGNORECASE)


def loaded_module_sha256(target, pattern=EXTENSION_NAME) -> str:
    """Observe one loaded module at session start; ambiguity stays unavailable.

    This hashes the loaded module's backing DLL, not relocated process memory
    and not a package receipt or a neighboring candidate file.
    """
    try:
        if not target_process_is_alive(target):
            return "unavailable"
        with WindowsProcessMemory.open(
            executable_names=(target.executable_path.name,),
            process_id=target.process_id,
            expected_sha256=target.executable_sha256,
        ) as process:
            matches = [module for module in process.modules() if pattern.fullmatch(module.name)]
            if len(matches) != 1:
                return "unavailable"
            with Path(matches[0].path).open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            return digest if target_process_is_alive(target) else "unavailable"
    except (OSError, RuntimeError, ValueError):
        return "unavailable"
