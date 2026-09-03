from __future__ import annotations

import hashlib
import json
import re
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
        [0.23, 0.24, 0.26],
        [0.54, 0.58, 0.65],
        [0.78, 0.81, 0.84],
        [1.0, 0.99, 0.95],
    ]

    samples = target["render_reference"]["samples"]
    for sample in samples:
        assert _sha256(ROOT / sample["atlas_path"]) == sample["atlas_sha256"]

    runtime = target["runtime_translation"]
    assert runtime["extension_version"] == "1.6.1"
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
        "wbBandThresholds.x - transitionWidth",
        "wbBandThresholds.y - transitionWidth",
        "wbBandThresholds.z - transitionWidth",
        "distantAlias * wbDistantHighlightCompression",
        "wbBandColor0",
        "wbBandColor1",
        "wbBandColor2",
        "wbBandColor3",
        "gl_Color.rgb",
        "gl_NormalMatrix * gl_Normal",
        "gl_FogFragCoord",
    ):
        assert token in shader
    defaults = (
        ROOT / "native" / "wonderbane_extension" / "graphics_control.cpp"
    ).read_text(encoding="utf-8")
    for token in (
        "{0.23F, 0.24F, 0.26F}",
        "{0.54F, 0.58F, 0.65F}",
        "{0.78F, 0.81F, 0.84F}",
        "{1.00F, 0.99F, 0.95F}",
        "parameters.depth_edge_threshold = 0.055F",
    ):
        assert token in defaults


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
    lab_start = (ROOT / "scripts" / "start-wonderbane-graphics-lab.ps1").read_text(
        encoding="utf-8"
    )
    assert 'RepositoryShare = "\\\\VBOXSVR\\codexrepo"' in publish
    assert 'ExtensionVersion = "1.6.13"' in publish
    assert "wonderbane-extension.dll" in publish
    assert r"\build\wonderbane-client-extension\Release" in publish
    assert "01e4297798c3c2ca4212d997f0793b8a4af0bb98d429f31d9e07a9dc029f42a4" in publish
    assert "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8" in publish
    assert "$extensionSha256 -cne $ExpectedExtensionSha256" in publish
    assert "$resultExecutableSha256 -cne $ExpectedExecutableSha256" in publish
    assert "patched_executable_sha256" in publish
    assert "--texture-patch-manifest $TexturePatchManifest" in publish
    assert "--texture-artifact-directory $TextureArtifactDirectory" in publish
    assert "texture_patch_manifest_sha256" in publish
    assert 'RepositoryShare = "\\\\VBOXSVR\\codexrepo"' in launch
    assert 'ExtensionVersion = "1.6.13"' in launch
    assert "39ee563be8e32353d60c6f9e3ebb801b8db1bffddb6dcb734fbd4f66b2285114" in launch
    assert '$expectedExtensionRelativePath = "wonderbane-extension.dll"' in launch
    assert 'Properties["extension_relative_path"]' in launch
    assert "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8" in launch
    assert 'Properties["result_executable_sha256"]' in launch
    assert "verify-runtime-copy" in launch
    assert manifest_sha256 in launch
    assert "wonderbane-1.0.5-55fbad5f.restrained-cel-v1" in launch
    assert "start-wonderbane-graphics-lab.ps1" in launch
    assert 'RepositoryShare = "\\\\VBOXSVR\\codexrepo"' in lab_start
    assert "WonderBane Graphics Lab is already running" in lab_start
    assert "Stop-Process" not in lab_start

    cel_shading = (
        ROOT / "native" / "wonderbane_extension" / "cel_shading.cpp"
    ).read_text(encoding="utf-8")
    assert "IsFeatureAccentDrawState" in cel_shading
    assert "array_planar_overlay_candidate" in cel_shading
    immediate_path = cel_shading.split(
        "void APIENTRY StrongBegin", 1
    )[1].split("void APIENTRY StrongEnd", 1)[0]
    assert "get_booleanv" not in immediate_path
    assert "g_fixed_function_state.depth_writes" in immediate_path
    assert "std::array<ImportHookPlan, 22U + kListStateCommandCount>" in cel_shading
    assert 'reinterpret_cast<PVOID>(&StrongPopAttrib)' in cel_shading
    assert '"glClear"' in cel_shading
    assert "BeginReviewedSceneUiBoundary" in cel_shading
    assert '"glEnable"' in cel_shading
    assert '"glDisable"' in cel_shading
    assert '"glDepthMask"' in cel_shading
    assert "InvalidateFixedFunctionState(&g_fixed_function_state)" in cel_shading


def test_required_renderer_imports_exist_in_reviewed_client() -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/renderer/wonderbane-55fb-opengl-imports.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["source_sha256"] == (
        "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc"
    )
    source = (ROOT / "native/wonderbane_extension/cel_shading.cpp").read_text(
        encoding="utf-8"
    )
    plans = source.split("std::array<ImportHookPlan,", 1)[1].split(
        "auto* const image =", 1
    )[0]
    entries = dict(re.findall(r'\{\s*"(gl\w+)"\s*,([^{}]*)\}', plans))
    required = {name for name, fields in entries.items()
                if not fields.rstrip().endswith("false,")}
    assert len(required) == 20
    assert required <= fixture["imports"].keys()
    assert "glPopAttrib" not in fixture["imports"]
    assert "glPopAttrib" in entries and "glPopAttrib" not in required
    assert '{"glPopAttrib", &g_pop_attrib, nullptr}' in source
    assert "&g_original_pop_attrib, &g_pop_attrib_slot, false" in plans
    # Macro-generated guards are optional too; a missing client symbol is not a
    # missing OpenGL helper or permission to replace an unexpected IAT target.
    assert "&g_list_original_##name, &g_list_slot_##name, false" in plans


def test_extension_version_is_consistent_across_every_runtime_surface() -> None:
    native = ROOT / "native" / "wonderbane_extension"
    cmake = (native / "CMakeLists.txt").read_text(encoding="utf-8")
    extension = (native / "extension.cpp").read_text(encoding="utf-8")
    graphics_status = (native / "graphics_status.cpp").read_text(encoding="utf-8")
    api = (native / "extension_api.h").read_text(encoding="utf-8")
    resource = (native / "extension.rc").read_text(encoding="utf-8")
    assert "project(wonderbane_extension VERSION 1.6.13" in cmake
    assert 'kExtensionVersion[] = "1.6.13"' in extension
    assert 'kExtensionVersion[] = "1.6.13"' in graphics_status
    assert "WONDERBANE_EXTENSION_VERSION_MAJOR 1U" in api
    assert "WONDERBANE_EXTENSION_VERSION_MINOR 6U" in api
    assert "WONDERBANE_EXTENSION_VERSION_PATCH 13U" in api
    assert "FILEVERSION 1,6,13,0" in resource
    assert "PRODUCTVERSION 1,6,13,0" in resource
    assert 'VALUE "FileVersion", "1.6.13.0\\0"' in resource
    assert 'VALUE "ProductVersion", "1.6.13.0\\0"' in resource
