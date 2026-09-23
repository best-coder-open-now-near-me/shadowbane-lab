import tempfile
import unittest
from pathlib import Path, PureWindowsPath

from shadowbane_lab.manager.runtime_paths import (
    GuestWindowsPath,
    HostRuntimePath,
    RootedRuntimePathMapper,
    RuntimePathDomainError,
)


class RuntimePathDomainTests(unittest.TestCase):
    def test_rooted_mapper_round_trips_without_implicit_path_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host_root = Path(directory).resolve()
            mapper = RootedRuntimePathMapper(
                host_root=HostRuntimePath(host_root),
                guest_root=GuestWindowsPath(PureWindowsPath(r"S:\WonderBaneState")),
            )
            host_runtime = HostRuntimePath(host_root / "client-runtimes" / "client-01")

            guest_runtime = mapper.host_to_guest(host_runtime)

            self.assertEqual(
                PureWindowsPath(r"S:\WonderBaneState\client-runtimes\client-01"),
                guest_runtime.path,
            )
            self.assertEqual(host_runtime, mapper.guest_to_host(guest_runtime))

    def test_mapper_rejects_paths_outside_either_authorized_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host_root = Path(directory).resolve()
            mapper = RootedRuntimePathMapper(
                host_root=HostRuntimePath(host_root),
                guest_root=GuestWindowsPath(PureWindowsPath(r"S:\WonderBaneState")),
            )
            with self.assertRaisesRegex(RuntimePathDomainError, "outside the mapped"):
                mapper.host_to_guest(HostRuntimePath(host_root.parent / "other"))
            with self.assertRaisesRegex(RuntimePathDomainError, "outside the mapped"):
                mapper.guest_to_host(
                    GuestWindowsPath(PureWindowsPath(r"T:\OtherState\client-01"))
                )

    def test_path_domains_reject_relative_and_unc_guest_paths(self) -> None:
        with self.assertRaisesRegex(RuntimePathDomainError, "host runtime path must be absolute"):
            HostRuntimePath(Path("relative"))
        with self.assertRaisesRegex(RuntimePathDomainError, "must be absolute"):
            GuestWindowsPath(PureWindowsPath("relative"))
        with self.assertRaisesRegex(RuntimePathDomainError, "guest-local drive"):
            GuestWindowsPath(PureWindowsPath(r"\\server\share\client-01"))

    def test_mapper_methods_require_typed_domains(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mapper = RootedRuntimePathMapper(
                host_root=HostRuntimePath(Path(directory).resolve()),
                guest_root=GuestWindowsPath(PureWindowsPath(r"S:\WonderBaneState")),
            )
            with self.assertRaisesRegex(RuntimePathDomainError, "requires HostRuntimePath"):
                mapper.host_to_guest(Path(directory))  # type: ignore[arg-type]
            with self.assertRaisesRegex(RuntimePathDomainError, "requires GuestWindowsPath"):
                mapper.guest_to_host(PureWindowsPath(r"S:\WonderBaneState"))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
