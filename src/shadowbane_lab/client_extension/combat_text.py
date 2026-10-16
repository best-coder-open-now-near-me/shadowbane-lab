"""Compile reviewed combat translations without changing localization lookup keys.

This creates an offline candidate, not an installed or live-qualified client.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

DATA_STRING_SHA256 = "4919261e7c9f9887bde63d128717849062eea7ce37214891676992c832b26845"


def replacements() -> dict[str, str]:
    """Exact reviewed keys; recovery classification requires native event context."""
    result: dict[str, str] = {}
    for resource in ("health", "vitality"):
        for source, target, original in (
            ("You", "%TARGETNAME%", f"Your weapon drains some of %TARGETNAME%'s {resource}!"),
            (
                "%CASTERNAME%",
                "%TARGETNAME%",
                f"%CASTERNAME%'s weapon drains some of %TARGETNAME%'s {resource}!",
            ),
            ("%CASTERNAME%", "You", f"%CASTERNAME%'s weapon drains some of your {resource}!"),
        ):
            result["Power:" + original] = (
                f"{source} -> {target}\\n%DAMAGEVAL% weapon {resource} drain"
            )
    for source, target, original in (
        (
            "You",
            "%TARGETNAME%",
            "Your %POWERNAME% burns %TARGETNAME% for %DAMAGEVAL% points of damage!",
        ),
        (
            "%CASTERNAME%",
            "%TARGETNAME%",
            "%CASTERNAME%'s %POWERNAME% burns %TARGETNAME% for %DAMAGEVAL% points of damage!",
        ),
        (
            "%CASTERNAME%",
            "You",
            "%CASTERNAME%'s %POWERNAME% burns you for %DAMAGEVAL% points of damage!",
        ),
    ):
        result["Power:" + original] = f"{source} -> {target}\\n%DAMAGEVAL% %POWERNAME%"
    return result


def compile_combat_text(original: bytes) -> bytes:
    """Preserve encoding, keys and unrelated bytes; reject unreviewed inputs."""
    if hashlib.sha256(original).hexdigest() != DATA_STRING_SHA256:
        raise ValueError("DataStringENGLISH.txt differs from the reviewed official resource")
    if not original.startswith(b"\xff\xfe"):
        raise ValueError("expected UTF-16LE BOM")
    result = original
    for key, value in replacements().items():
        # The lookup key is itself the original English sentence. Replacing it
        # would silently defeat localization, so change only the second field.
        old = f'"{key}" "{key.removeprefix("Power:")}"'.encode("utf-16le")
        new = f'"{key}" "{value}"'.encode("utf-16le")
        if result.count(old) != 1:
            raise ValueError(f"expected exactly one original translation: {key}")
        result = result.replace(old, new, 1)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Reviewed official DataStringENGLISH.txt")
    parser.add_argument("output", type=Path, help="New offline candidate file; must not exist")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("output must differ from source")
    result = compile_combat_text(args.source.read_bytes())
    # Exclusive creation prevents overwriting original assets or an earlier
    # candidate. No runtime writer or retained deployment fallback is involved.
    with args.output.open("xb") as stream:
        stream.write(result)
    print(
        f"candidate_sha256={hashlib.sha256(result).hexdigest()} translations=9 live_qualified=false"
    )


if __name__ == "__main__":
    main()
