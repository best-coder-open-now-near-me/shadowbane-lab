from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class DiagnosticsClientBoundaryTests(unittest.TestCase):
    def test_build_profile_excludes_active_extension_features(self) -> None:
        cmake = _text("native/wonderbane_extension/CMakeLists.txt")
        extension = _text("native/wonderbane_extension/extension.cpp")
        renderer = _text("native/wonderbane_extension/cel_shading.cpp")
        camera = _text("native/wonderbane_extension/camera_observation.cpp")
        probe = _text("native/wonderbane_extension/probe.cpp")

        self.assertIn('WONDERBANE_EXTENSION_PROFILE "full"', cmake)
        self.assertIn("camera_observation.cpp", cmake)
        self.assertIn("PROPERTY STRINGS full diagnostics-only", cmake)
        self.assertIn("WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY=1", cmake)
        self.assertIn("#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)", extension)
        self.assertIn("StartGraphicsPresentObservation()", extension)
        self.assertIn("StartPassiveCameraObservation()", extension)
        self.assertIn("StopPassiveCameraObservation()", extension)
        self.assertIn("StartStrongCelShading()", extension)
        self.assertIn("&& !kDiagnosticsOnly", extension)
        self.assertIn('"diagnostics-only"', renderer)
        self.assertIn('"full-renderer"', renderer)
        for symbol in ("glBegin", "glCallList", "glDrawArrays", "glDrawElements"):
            self.assertIn(f'"{symbol}"', camera)
        self.assertIn("kGlModelViewStackDepth", camera)
        self.assertIn("model_view_stack_depth != 1", camera)
        self.assertIn("ObserveGraphicsCameraState(", camera)
        self.assertIn("ReplaceImportAddressSlot(", camera)
        for forbidden in (
            "glEnable(", "glDisable(", "glDepthMask(", "glBindTexture(",
            "glCopyTex", "glReadPixels(", "WriteProcessMemory(",
        ):
            self.assertNotIn(forbidden, camera)
        self.assertIn("event channel absence validation", probe)

    def test_publication_has_no_graphics_experiment_or_listener_path(self) -> None:
        publish = _text("scripts/publish-wonderbane-diagnostics-client.ps1")
        launch = _text("scripts/launch-wonderbane-diagnostics-client.ps1")
        combined = publish + launch

        self.assertIn('ExtensionVersion = "1.6.2"', publish)
        self.assertIn(
            "d281a9ab7af2286d7353186ee0f67af2b3d35d4bd9adadeaf58f4121dd9b54fe",
            publish,
        )
        self.assertIn('runtime_profile = "diagnostics-only"', publish)
        self.assertIn("baseline_payload_retained = $false", publish)
        self.assertIn("Remove-ExactTransientBaseline", publish)
        self.assertIn("verify-copy", publish)
        self.assertIn("verify-launchable-copy", launch)
        self.assertIn('"wait-graphics-status"', launch)
        self.assertIn('"--runtime-profile", "diagnostics-only"', launch)
        self.assertIn("Start-Process @startArguments", launch)
        self.assertIn("Join-Path $env:USERPROFILE", publish)
        self.assertIn('"Wonderbane-diagnostics-wb-', publish)
        self.assertNotIn('"S:\\Wonderbane-diagnostics-', publish)
        self.assertIn('[string] $InstanceId = "primary"', publish)
        self.assertIn('[string] $InstanceId = "primary"', launch)
        self.assertIn("current-$InstanceId.json", publish)
        self.assertIn("current-$InstanceId.json", launch)
        self.assertIn("instance_id = $InstanceId", publish)
        self.assertIn("[string] $receipt.instance_id -ne $InstanceId", launch)
        self.assertIn("[IO.Path]::GetFullPath($runningPath)", launch)
        self.assertIn("[StringComparison]::OrdinalIgnoreCase", launch)
        self.assertNotIn('if (Get-Process -Name "sb"', combined)
        for forbidden in (
            "TexturePatchManifest",
            "TextureArtifactDirectory",
            "LIBGL_ALWAYS_SOFTWARE",
            "GALLIUM_DRIVER",
            "llvmpipe",
            "listen-go",
            "control-center",
            "world-map",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
