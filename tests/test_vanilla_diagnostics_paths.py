from __future__ import annotations

import ctypes
import hashlib
import os
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

from shadowbane_vanilla_diagnostics.capture import (
    CaptureError,
    _assert_exact_identity,
    assert_required_output_root,
)
from shadowbane_vanilla_diagnostics.model import ProcessIdentity
from shadowbane_vanilla_diagnostics.paths import same_windows_path
from shadowbane_vanilla_diagnostics.residue import build_vanilla_preflight


class VanillaPathTests(unittest.TestCase):
    def test_aliases_are_compared_after_filesystem_resolution(self) -> None:
        short = r"C:\Users\RUNNER~1\game\sb.exe"
        long = r"C:\Users\runneradmin\game\sb.exe"
        with patch(
            "shadowbane_vanilla_diagnostics.paths.os.path.realpath",
            return_value=long,
        ) as resolve:
            self.assertTrue(same_windows_path(short, long))
        self.assertEqual([short, long], [call.args[0] for call in resolve.call_args_list])

    def test_resolution_errors_fail_closed(self) -> None:
        with patch(
            "shadowbane_vanilla_diagnostics.paths.os.path.realpath",
            side_effect=OSError("unreadable path"),
        ):
            self.assertFalse(same_windows_path("first/sb.exe", "second/sb.exe"))
        self.assertFalse(same_windows_path("", ""))
        self.assertFalse(same_windows_path("bad\0path", "bad\0path"))

    def test_same_bytes_at_another_path_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.exe", Path(directory) / "second.exe"
            first.write_bytes(b"identical")
            second.write_bytes(b"identical")
            self.assertFalse(same_windows_path(first, second))
            with self.assertRaisesRegex(CaptureError, "executable path changed"):
                _assert_exact_identity(
                    ProcessIdentity(42, 100, str(first)),
                    ProcessIdentity(42, 100, str(second)),
                )

    def test_output_reparse_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            package = root / "package"
            outside = root / "outside"
            package.mkdir()
            outside.mkdir()
            try:
                (package / "evidence").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlink creation is unavailable")
            with self.assertRaisesRegex(CaptureError, "escapes"):
                assert_required_output_root(
                    package / "evidence",
                    r"{PACKAGE_ROOT}\evidence",
                    package_root=package,
                )

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 path integration")
    def test_real_short_alias_preserves_preflight_output_and_lifetime_checks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shadowbane-path-alias-") as directory:
            root = Path(directory).resolve()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_short_path = kernel32.GetShortPathNameW
            get_short_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
            get_short_path.restype = wintypes.DWORD
            buffer = ctypes.create_unicode_buffer(32768)
            length = get_short_path(str(root), buffer, len(buffer))
            if (
                not length
                or length >= len(buffer)
                or buffer.value.casefold() == str(root).casefold()
            ):
                self.skipTest("filesystem does not provide an 8.3 alias")
            alias = Path(buffer.value)
            executable = root / "sb.exe"
            executable.write_bytes(b"vanilla")
            identity = ProcessIdentity(42, 100, str(alias / "sb.exe"))
            report = build_vanilla_preflight(
                requested_executable=executable,
                identity=identity,
                allowed_executable_sha256=[hashlib.sha256(b"vanilla").hexdigest()],
                modules=[{"name": "sb.exe", "path": str(alias / "sb.exe"), "image_size": 7}],
                runtime_status_directory=None,
            )
            self.assertTrue(report["accepted"], report["failures"])
            assert_required_output_root(
                alias / "evidence",
                r"{PACKAGE_ROOT}\evidence",
                package_root=root,
            )
            _assert_exact_identity(identity, ProcessIdentity(42, 100, str(executable)))
            with self.assertRaisesRegex(CaptureError, "lifetime changed"):
                _assert_exact_identity(identity, ProcessIdentity(42, 101, str(executable)))
            with self.assertRaisesRegex(CaptureError, "portable evidence"):
                assert_required_output_root(
                    alias / "elsewhere",
                    r"{PACKAGE_ROOT}\evidence",
                    package_root=root,
                )
