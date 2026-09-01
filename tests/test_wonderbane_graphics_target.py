from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "evidence" / "graphics" / "restrained-cel-v1" / "target.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_restrained_cel_target_is_pinned_end_to_end() -> None:
    target = json.loads(TARGET.read_text(encoding="utf-8"))
    assert target["schema_version"] == 1
    assert target["target_id"] == "wonderbane-55fb-restrained-cel-v1"
    assert target["approved_source"]["label"] == "RESTRAINED CEL"
    assert target["approved_source"]["variant"] == "cel_subtle"

    visual = target["approved_source"]["visual_reference"]
    assert _sha256(ROOT / visual["path"]) == visual["sha256"]

    bands = target["render_reference"]["color_bands"]
    assert [item["upper_bound_exclusive"] for item in bands] == [
        0.22,
        0.43,
        0.66,
        None,
    ]
    assert [item["color"] for item in bands] == [
        [0.2, 0.2, 0.2],
        [0.48, 0.53, 0.61],
        [0.72, 0.76, 0.8],
        [1.0, 0.98, 0.92],
    ]

    samples = target["render_reference"]["samples"]
    for sample in samples:
        assert _sha256(ROOT / sample["atlas_path"]) == sample["atlas_sha256"]

    runtime = target["runtime_translation"]
    assert runtime["extension_version"] == "1.5.7"
    assert runtime["depth_edge_radius_pixels"] == 1.0
    assert "inverse-eye-depth curvature" in runtime["depth_edge_source"]
    manifest_path = ROOT / runtime["texture_manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["patch_id"] == runtime["texture_patch_id"]
    assert {
        item["resource_id"]: item["artifact_sha256"]
        for item in manifest["replacements"]
    } == {
        item["texture_resource_id"]: item["atlas_sha256"] for item in samples
    }

    shader = (
        ROOT / "native" / "wonderbane_extension" / "banded_lighting.cpp"
    ).read_text(encoding="utf-8")
    for token in (
        "fwidth(intensity)",
        "smoothstep(0.22 - transitionWidth",
        "smoothstep(0.43 - transitionWidth",
        "smoothstep(0.66 - transitionWidth",
        "distantAlias * 0.45",
        "vec3(0.20, 0.20, 0.20)",
        "vec3(0.48, 0.53, 0.61)",
        "vec3(0.72, 0.76, 0.80)",
        "vec3(1.00, 0.98, 0.92)",
        "gl_Color.rgb",
        "gl_NormalMatrix * gl_Normal",
        "gl_FogFragCoord",
    ):
        assert token in shader


def test_graphics_publication_and_launch_pin_the_golden_package() -> None:
    manifest_path = (
        ROOT
        / "assets"
        / "wonderbane_graphics"
        / "restrained-cel-v1"
        / "texture-patches.json"
    )
    manifest_sha256 = _sha256(manifest_path)
    publish = (ROOT / "scripts" / "publish-wonderbane-graphics-baseline.ps1").read_text(
        encoding="utf-8"
    )
    launch = (ROOT / "scripts" / "launch-wonderbane-graphics-baseline.ps1").read_text(
        encoding="utf-8"
    )
    assert 'ExtensionVersion = "1.5.7"' in publish
    assert "wonderbane-extension-1.5.7.dll" in publish
    assert r"\build\wonderbane-client-extension\Release" in publish
    assert "67a10b2b414c4fb94f6d40aa916ea1610f5daa7e24e3accdfb4bf917bbb8c936" in publish
    assert "$extensionSha256 -cne $ExpectedExtensionSha256" in publish
    assert "--texture-patch-manifest $TexturePatchManifest" in publish
    assert "--texture-artifact-directory $TextureArtifactDirectory" in publish
    assert "texture_patch_manifest_sha256" in publish
    assert 'ExtensionVersion = "1.5.7"' in launch
    assert "67a10b2b414c4fb94f6d40aa916ea1610f5daa7e24e3accdfb4bf917bbb8c936" in launch
    assert '$expectedExtensionRelativePath = "wonderbane-extension-1.5.7.dll"' in launch
    assert 'Properties["extension_relative_path"]' in launch
    assert "a8b2693fb3e11332b95d0ef6dd02bf418f133a10f505be642c3623180d41896f" in launch
    assert 'Properties["result_executable_sha256"]' in launch
    assert "verify-copy" in launch
    assert manifest_sha256 in launch
    assert "wonderbane-1.0.5-55fbad5f.restrained-cel-v1" in launch
