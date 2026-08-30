import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeTargetIdentityCompatibilityError,
    NativeTargetIdentityObservation,
    NativeTargetIdentityProfile,
    NativeTargetIdentityReader,
    NativeTargetIdentityReadError,
    load_bundled_native_target_identity_profile,
    load_native_target_identity_profile_text,
    open_windows_native_target_identity_reader,
)


def _profile() -> NativeTargetIdentityProfile:
    return NativeTargetIdentityProfile(
        profile_id="target-identity-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        selected_pointer_rva=0x100,
        arc_character_vtable_rva=0x200,
        sparse_data_offset=0x34,
        merchant_data_descriptor_rva=0x2F0,
        shopkeeper_descriptor_rva=0x300,
        banker_descriptor_rva=0x310,
        trainer_descriptor_rva=0x320,
        minion_descriptor_rva=0x330,
        descriptor_key_offset=4,
        sparse_value_pointer_offset=4,
        maximum_sparse_table_bits=8,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
    )


class FakeProcessMemory:
    pid = 41
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    target = 0x12400000
    buckets = 0x12500000

    def __init__(self, profile: NativeTargetIdentityProfile) -> None:
        self.profile = profile
        self.closed = False
        self.selected = self.target
        self.selected_vtable = self.base_address + profile.arc_character_vtable_rva
        self.table_bits = 2
        self.descriptor_keys = {
            "merchant": 0x1000,
            "shopkeeper": 0x1001,
            "banker": 0x1002,
            "trainer": 0x1003,
            "minion": 0x1004,
        }
        self.role_values: dict[str, int] = {}
        self.role_nodes = {
            role: 0x12600000 + index * 0x100 for index, role in enumerate(self.descriptor_keys)
        }
        self.role_value_pointers = {
            role: 0x12700000 + index * 0x100 for index, role in enumerate(self.descriptor_keys)
        }

    def read(self, address: int, size: int) -> bytes:
        descriptor_rvas = {
            "merchant": self.profile.merchant_data_descriptor_rva,
            "shopkeeper": self.profile.shopkeeper_descriptor_rva,
            "banker": self.profile.banker_descriptor_rva,
            "trainer": self.profile.trainer_descriptor_rva,
            "minion": self.profile.minion_descriptor_rva,
        }
        for role, rva in descriptor_rvas.items():
            if address == self.base_address + rva + self.profile.descriptor_key_offset:
                return struct.pack("<I", self.descriptor_keys[role])
        if address == self.base_address + self.profile.selected_pointer_rva:
            return struct.pack("<I", self.selected)
        if address == self.selected:
            return struct.pack("<I", self.selected_vtable)
        if address == self.selected + self.profile.sparse_data_offset:
            bucket_pointer = self.buckets if self.role_values else 0
            return struct.pack("<II", bucket_pointer, self.table_bits)
        if address == self.buckets:
            entries = [
                (self.descriptor_keys[role], self.role_nodes[role]) for role in self.role_values
            ]
            entries.extend([(0, 0)] * ((1 << self.table_bits) - len(entries)))
            raw = b"".join(struct.pack("<II", *entry) for entry in entries)
            if len(raw) != size:
                raise AssertionError(f"unexpected table read size {size}")
            return raw
        for role, node in self.role_nodes.items():
            if address == node + self.profile.sparse_value_pointer_offset:
                return struct.pack("<I", self.role_value_pointers[role])
        for role, value_pointer in self.role_value_pointers.items():
            if address == value_pointer:
                return bytes((self.role_values[role],))
        raise AssertionError(f"unexpected read at 0x{address:X} ({size} bytes)")

    def close(self) -> None:
        self.closed = True


class NativeTargetIdentityReaderTests(unittest.TestCase):
    def test_opens_the_guarded_process_explicitly(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        with patch(
            "shadowbane_lab.client_observation.native_target_identity."
            "WindowsReadOnlyProcessMemory.open_for_process",
            return_value=process,
        ) as open_for_process:
            reader = open_windows_native_target_identity_reader(
                profile,
                process_id=4320,
            )

        open_for_process.assert_called_once_with("sb.exe", 4320)
        reader.close()
        self.assertTrue(process.closed)

    def test_absent_selection_has_no_identity_state(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.selected = 0

        observation = NativeTargetIdentityReader(profile, process).observe()

        self.assertEqual(NativeTargetIdentityObservation(target_present=False), observation)
        self.assertFalse(observation.attack_eligible)

    def test_missing_sparse_values_use_native_false_defaults(self) -> None:
        profile = _profile()
        observation = NativeTargetIdentityReader(
            profile,
            FakeProcessMemory(profile),
        ).observe()

        self.assertTrue(observation.target_present)
        self.assertTrue(observation.attack_eligible)
        self.assertEqual((), observation.protected_roles)

    def test_observes_each_protected_native_role(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.role_values = {
            "shopkeeper": 1,
            "banker": 0,
            "trainer": 1,
            "minion": 1,
        }

        observation = NativeTargetIdentityReader(profile, process).observe()

        self.assertEqual(("shopkeeper", "trainer", "minion"), observation.protected_roles)
        self.assertFalse(observation.attack_eligible)
        self.assertTrue(observation.trainer)
        self.assertFalse(observation.banker)

    def test_merchant_data_presence_is_protected_without_bool_dereference(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.role_values = {"merchant": 99}

        observation = NativeTargetIdentityReader(profile, process).observe()

        self.assertTrue(observation.merchant)
        self.assertEqual(("merchant",), observation.protected_roles)
        self.assertFalse(observation.attack_eligible)

    def test_non_boolean_sparse_value_fails_closed(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.role_values = {"trainer": 2}

        with self.assertRaisesRegex(NativeTargetIdentityReadError, "not boolean"):
            NativeTargetIdentityReader(profile, process).observe()

    def test_oversized_sparse_table_fails_closed(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.role_values = {"trainer": 1}
        process.table_bits = profile.maximum_sparse_table_bits + 1

        with self.assertRaisesRegex(NativeTargetIdentityReadError, "calibrated bound"):
            NativeTargetIdentityReader(profile, process).observe()

    def test_non_character_selection_is_explicitly_ineligible(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.selected_vtable += 4

        observation = NativeTargetIdentityReader(profile, process).observe()

        self.assertFalse(observation.arc_character)
        self.assertFalse(observation.attack_eligible)

    def test_unavailable_classification_is_explicit_and_fail_closed(self) -> None:
        observation = NativeTargetIdentityObservation.unavailable(
            target_token="unreadable-target",
            error="NativeTargetIdentityReadError:unmapped sparse table",
        )

        self.assertTrue(observation.target_present)
        self.assertFalse(observation.classification_available)
        self.assertEqual(
            "NativeTargetIdentityReadError:unmapped sparse table",
            observation.classification_error,
        )
        self.assertIsNone(observation.arc_character)
        self.assertEqual((), observation.protected_roles)
        self.assertFalse(observation.attack_eligible)

    def test_executable_hash_mismatch_fails_before_descriptor_reads(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeTargetIdentityCompatibilityError, "SHA-256"):
            NativeTargetIdentityReader(profile, process)


class NativeTargetIdentityProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_reverse_engineered_offsets(self) -> None:
        profile = load_bundled_native_target_identity_profile()

        self.assertEqual("sb.exe", profile.executable_name)
        self.assertEqual(0x16A2DA4, profile.selected_pointer_rva)
        self.assertEqual(0x114165C, profile.arc_character_vtable_rva)
        self.assertEqual(0x34, profile.sparse_data_offset)
        self.assertEqual(0x1373238, profile.merchant_data_descriptor_rva)
        self.assertEqual(0x13732A8, profile.shopkeeper_descriptor_rva)
        self.assertEqual(0x1373098, profile.banker_descriptor_rva)
        self.assertEqual(0x1373080, profile.trainer_descriptor_rva)
        self.assertEqual(0x13730B0, profile.minion_descriptor_rva)

    def test_unknown_profile_field_fails_closed(self) -> None:
        profile = _profile()
        payload = {
            field: getattr(profile, field)
            for field in NativeTargetIdentityProfile.__dataclass_fields__
        }
        payload["surprise"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_target_identity_profile_text(json.dumps(payload))


class FakeNativeTargetIdentityReader:
    process_id = 4320

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def observe(self) -> NativeTargetIdentityObservation:
        return NativeTargetIdentityObservation(
            target_present=True,
            arc_character=True,
            merchant=False,
            shopkeeper=False,
            banker=False,
            trainer=True,
            minion=False,
            target_token="trainer-token",
        )


class NativeTargetIdentityCliTests(unittest.TestCase):
    def test_json_observation_reports_attack_eligibility(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.open_windows_native_target_identity_reader",
                return_value=FakeNativeTargetIdentityReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-target-identity", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(["trainer"], payload["protected_roles"])
        self.assertTrue(payload["classification_available"])
        self.assertIsNone(payload["classification_error"])
        self.assertFalse(payload["attack_eligible"])


if __name__ == "__main__":
    unittest.main()
