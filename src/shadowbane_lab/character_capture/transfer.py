"""Read-only character transfer evidence: native records plus guided gear screenshots.

A bundle is evidence for reconciliation, never an executable database import.
No client input, process writes, debugger attachment, or server connection occurs.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_input.window import WindowsForegroundWindowInspector
from shadowbane_lab.client_observation.native_character_config import NativeCharacterConfigReader
from shadowbane_lab.client_observation.native_character_session import NativeCharacterSession
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_snapshot import (
    NativePlayerSnapshotReader,
    load_bundled_native_player_snapshot_profiles,
)

UNRESOLVED = [
    "race_base_class_promotion",
    "base_attributes_and_allocations",
    "creation_runes_and_disciplines",
    "equipped_slots_templates_and_item_effects",
    "destination_content_mapping",
]
SECTIONS = (
    (
        "character-sheet",
        "Character sheet: race/classes, level, attributes and derived stats. "
        "Capture extra pages/tooltips for base versus modified values.",
    ),
    ("runes", "All applied creation runes and disciplines; scroll or open tooltips as needed."),
    ("equipment-overview", "Equipment panel showing every occupied and empty slot."),
    (
        "equipment-item",
        "A readable tooltip for EACH equipped item, including both weapons, "
        "armor and jewelry. Label each by slot. Capture extra images if text does not fit.",
    ),
)


class CaptureError(RuntimeError):
    pass


def _now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _build_signature(snapshot):
    """Ignore changing vitals/buffs; compare level, unspent points and actual training."""
    progression = snapshot["progression"]
    return (
        tuple(
            progression[key]
            for key in ("level", "unspent_ability_points", "unspent_training_points")
        ),
        tuple(
            tuple(sorted((row["token"], row["trained_rank"]) for row in snapshot["training"][kind]))
            for kind in ("skills", "powers")
        ),
    )


def observe_character(session, reader):
    session.require_current()
    first = reader.observe()
    session.require_current()
    second = reader.observe()
    session.require_current()
    binding = session.binding
    for snapshot in (first, second):
        if (
            snapshot.exact_process_identity
            != (binding.process_id, binding.process_creation_filetime_utc)
            or snapshot.executable_sha256 != binding.executable_sha256
        ):
            raise CaptureError("Snapshot belongs to a different process lifetime or executable.")
    if _build_signature(first.as_dict()) != _build_signature(second.as_dict()):
        raise CaptureError("Training or level changed during capture; stop training and retry.")
    return {
        "schema_version": 1,
        "source": binding.as_dict(),
        "native_snapshot": second.as_dict(),
        "unresolved_structured_fields": list(UNRESOLVED),
        "database_import_ready": False,
    }


class CaptureBundle:
    def __init__(self, output_root, character):
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", character["source"]["character_name"])[:48]
        name = f"{slug}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        self.path = Path(output_root).resolve() / name
        self.path.mkdir(parents=True, exist_ok=False)
        self.manifest = {
            "format": "shadowbane.character-transfer",
            "schema_version": 1,
            "created_at_utc": _now(),
            "capture_status": "collecting",
            "database_import_ready": False,
            "source": character["source"],
            "unresolved_structured_fields": list(UNRESOLVED),
            "files": [],
            "sections": {},
            "notes": [
                "Screenshots require transcription and comparison with destination content.",
                "Effective ranks and ratings may include equipment and active buffs.",
                "No bank, vault, nested-container or complete inventory capture is claimed.",
                "Do not execute this evidence as SQL. Source instance IDs must be remapped.",
            ],
        }
        self.add_file("character.json", _encoded(character), kind="native-character")
        self.save()

    def add_file(self, name, content, **metadata):
        if Path(name).name != name or name in ("manifest.json", ".manifest.tmp"):
            raise ValueError("Evidence filename must be a simple reserved-safe basename.")
        with (self.path / name).open("xb") as stream:
            stream.write(content)
        self.manifest["files"].append(
            {
                "path": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                **metadata,
            }
        )

    def save(self):
        # Atomic replacement for this write only; never a retained backup.
        temporary = self.path / ".manifest.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(_encoded(self.manifest))
            os.replace(temporary, self.path / "manifest.json")
        finally:
            if temporary.exists():
                temporary.unlink()

    def finish(self, status, error=None):
        self.manifest["capture_status"] = status
        self.manifest["finished_at_utc"] = _now()
        if error:
            self.manifest["error"] = str(error)
        self.save()


def capture_frame(session, inspector, grab):
    session.require_current()
    before = inspector.inspect()
    binding = session.binding
    if (
        before is None
        or not before.is_foreground
        or not before.is_visible
        or before.executable_name.casefold() != "sb.exe"
        or before.process_id != binding.process_id
        or before.process_started_at_100ns != binding.process_creation_filetime_utc
        or not before.window_handle
    ):
        raise CaptureError("Bring the bound game window to the foreground and retry.")
    bounds = before.client_bounds
    picture = grab(
        bbox=(bounds.left, bounds.top, bounds.left + bounds.width, bounds.top + bounds.height),
        all_screens=True,
    )
    after = inspector.inspect()
    session.require_current()
    if after != before:
        raise CaptureError("Game window changed during the screenshot; retry.")
    if picture.size != (bounds.width, bounds.height):
        raise CaptureError("Screenshot dimensions do not match the game client area.")
    if picture.convert("RGB").getextrema() == ((0, 0), (0, 0), (0, 0)):
        raise CaptureError("Screenshot is black; use windowed mode and retry.")
    stream = io.BytesIO()
    picture.save(stream, format="PNG")
    return stream.getvalue(), {"width": bounds.width, "height": bounds.height}


@contextmanager
def _physical_pixels():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    change = user32.SetThreadDpiAwarenessContext
    change.argtypes = (ctypes.c_void_p,)
    change.restype = ctypes.c_void_p
    previous = change(ctypes.c_void_p(-4))
    if not previous:
        raise OSError("Cannot establish physical-pixel screenshot coordinates.")
    try:
        yield
    finally:
        change(previous)


def guided_evidence(bundle, session, delay):
    from PIL import ImageGrab

    print("\nStay on this character; do not train, level, equip or unequip during capture.")
    print("Hide chat if you do not want it in the pictures. Only the game client area is saved.")
    print(
        "For each image: enter a label here, then focus the game and display the requested panel."
    )
    print("Return to this console after the countdown. Type /done to finish a section.")
    with _physical_pixels():
        inspector = WindowsForegroundWindowInspector()
        for section, instructions in SECTIONS:
            print(f"\n{instructions}")
            count = 0
            while True:
                label = input(f"{section}: image label, or /done: ").strip()
                if label == "/done":
                    bundle.manifest["sections"][section] = {
                        "images": count,
                        "status": "needs_visual_review" if count else "not_captured",
                    }
                    bundle.save()
                    break
                if not label or len(label) > 200:
                    print("Enter a label of 1-200 characters, such as 'left ring tooltip'.")
                    continue
                print(f"Focus the game now. Capturing in {delay} seconds...", flush=True)
                time.sleep(delay)
                # A lost character binding is fatal; a missed focus can be retried.
                session.require_current()
                try:
                    content, dimensions = capture_frame(session, inspector, ImageGrab.grab)
                except CaptureError as exc:
                    print(f"No image saved: {exc}")
                    continue
                index = len(bundle.manifest["files"])
                bundle.add_file(
                    f"{index:03d}-{section}.png",
                    content,
                    kind="screenshot",
                    section=section,
                    label=label,
                    captured_at_utc=_now(),
                    **dimensions,
                )
                count += 1
                bundle.save()
                print(f"Saved {section} image {count}.")


def run_capture(arguments):
    process = (
        WindowsReadOnlyProcessMemory.open_unique("sb.exe")
        if arguments.pid is None
        else WindowsReadOnlyProcessMemory.open_for_process("sb.exe", arguments.pid)
    )
    bundle = None
    try:
        session = NativeCharacterSession(NativeCharacterConfigReader(process))
        identity = session.binding.identity
        if identity.character_name.casefold() != arguments.character.casefold():
            raise CaptureError(
                f"Expected {arguments.character!r}; logged in as {identity.character_name!r}."
            )
        if identity.server_name.casefold() != arguments.server.casefold():
            raise CaptureError(
                f"Expected server {arguments.server!r}; found {identity.server_name!r}."
            )
        reader = NativePlayerSnapshotReader(load_bundled_native_player_snapshot_profiles(), process)
        character = observe_character(session, reader)
        bundle = CaptureBundle(arguments.output_root, character)
        print(f"Capturing {identity.character_name} on {identity.server_name}.")
        print(f"Local bundle: {bundle.path}")
        if not arguments.native_only:
            guided_evidence(bundle, session, arguments.delay)
        final = observe_character(session, reader)
        if _build_signature(character["native_snapshot"]) != _build_signature(
            final["native_snapshot"]
        ):
            raise CaptureError(
                "Build changed during the session. Capture it again without training."
            )
        bundle.add_file("character-final.json", _encoded(final), kind="native-character-final")
        bundle.finish("review_required")
        print(f"Capture saved: {bundle.path}")
        print(
            "Transfer this entire folder. Gear/runes/base attributes require review and "
            "transcription before database import; this is not an import-ready build."
        )
        return 0
    except BaseException as exc:
        if bundle is not None:
            bundle.finish(
                "interrupted" if isinstance(exc, (KeyboardInterrupt, EOFError)) else "failed",
                str(exc) or type(exc).__name__,
            )
            print(f"Incomplete evidence retained locally: {bundle.path}", file=sys.stderr)
        raise
    finally:
        process.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", required=True, help="expected logged-in character name")
    parser.add_argument("--server", default="Wonderbane", help="expected source server name")
    parser.add_argument("--pid", type=int, help="required when multiple sb.exe clients are running")
    parser.add_argument("--output-root", type=Path, default=Path("captures/character-transfer"))
    parser.add_argument("--delay", type=int, default=8, help="seconds to focus game (3-60)")
    parser.add_argument(
        "--native-only",
        action="store_true",
        help="skip pictures; equipment/runes/attributes will remain uncaptured",
    )
    arguments = parser.parse_args(argv)
    if not arguments.character.strip() or not arguments.server.strip():
        parser.error("character and server must be nonempty")
    if not 3 <= arguments.delay <= 60 or (arguments.pid is not None and arguments.pid <= 0):
        parser.error("delay must be 3-60 seconds and pid must be positive")
    try:
        return run_capture(arguments)
    except (KeyboardInterrupt, EOFError):
        print("Capture interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
