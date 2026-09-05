from __future__ import annotations

import unittest

from shadowbane_lab.client_observation.build_compatibility import (
    NativeLayoutCompatibilityRegistryError,
    canonical_native_layout_sha256,
    native_layout_is_compatible,
)


class NativeBuildCompatibilityTests(unittest.TestCase):
    def test_exact_digest_is_compatible_without_registry_membership(self) -> None:
        digest = "ab" * 32

        self.assertTrue(native_layout_is_compatible(digest, digest.upper()))

    def test_reviewed_wonderbane_patch_builds_share_native_layout(self) -> None:
        canonical = "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13"
        pre_patch = "2b186aef864ea1ce16d8ec959c450f1f2e301d1ba25d9daa3b14ab6c65d68c3d"
        text_fixed = "e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96"
        bootstrapped = "b392d2a5265bbe674f74fe1f80a096992148dedeb33069cf63181dc22ca419cf"
        patched_20260831 = "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc"
        bootstrapped_20260831 = (
            "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8"
        )

        self.assertTrue(native_layout_is_compatible(canonical, pre_patch))
        self.assertTrue(native_layout_is_compatible(pre_patch, text_fixed))
        self.assertTrue(native_layout_is_compatible(text_fixed, bootstrapped))
        self.assertTrue(native_layout_is_compatible(bootstrapped, canonical))
        self.assertTrue(native_layout_is_compatible(text_fixed, patched_20260831))
        self.assertTrue(native_layout_is_compatible(patched_20260831, bootstrapped_20260831))
        self.assertEqual(canonical, canonical_native_layout_sha256(bootstrapped_20260831))

    def test_current_version_update_preserves_reviewed_layout(self) -> None:
        for digest in (
            "feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff",
            "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87",
        ):
            self.assertTrue(native_layout_is_compatible(
                "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc", digest
            ))

    def test_unreviewed_build_is_its_own_canonical_layout(self) -> None:
        digest = "ab" * 32

        self.assertEqual(digest, canonical_native_layout_sha256(digest.upper()))

    def test_unreviewed_build_is_rejected(self) -> None:
        canonical = "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13"

        self.assertFalse(native_layout_is_compatible(canonical, "cd" * 32))

    def test_malformed_digest_is_rejected(self) -> None:
        with self.assertRaises(NativeLayoutCompatibilityRegistryError):
            native_layout_is_compatible("not-a-digest", "ab" * 32)


if __name__ == "__main__":
    unittest.main()
