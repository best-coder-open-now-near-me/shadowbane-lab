"""Read-only WonderBane character discovery and snapshot capture."""

from shadowbane_lab.character_capture.collector import (
    CharacterCaptureError,
    capture_character,
)
from shadowbane_lab.character_capture.layout import (
    AddressExpression,
    AddressStep,
    CharacterLayout,
    CharacterLayoutError,
    CollectionSpec,
    RecordSpec,
    TargetSpec,
    ValueSpec,
    load_character_layout,
)
from shadowbane_lab.character_capture.memory import (
    BufferMemoryReader,
    MemoryAccessError,
    MemoryReader,
    ProcessSelectionError,
    WindowsProcessMemory,
)
from shadowbane_lab.character_capture.model import (
    CharacterCapture,
    MemoryRegion,
    ModuleInfo,
    ProcessInfo,
    ScanMatch,
)

__all__ = [
    "AddressExpression",
    "AddressStep",
    "BufferMemoryReader",
    "CharacterCapture",
    "CharacterCaptureError",
    "CharacterLayout",
    "CharacterLayoutError",
    "CollectionSpec",
    "MemoryAccessError",
    "MemoryReader",
    "MemoryRegion",
    "ModuleInfo",
    "ProcessInfo",
    "ProcessSelectionError",
    "RecordSpec",
    "ScanMatch",
    "TargetSpec",
    "ValueSpec",
    "WindowsProcessMemory",
    "capture_character",
    "load_character_layout",
]
