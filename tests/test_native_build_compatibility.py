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
        patched = "e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96"

        self.assertTrue(native_layout_is_compatible(canonical, pre_patch))
        self.assertTrue(native_layout_is_compatible(pre_patch, patched))
        self.assertTrue(native_layout_is_compatible(patched, canonical))
        self.assertEqual(canonical, canonical_native_layout_sha256(patched))

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
