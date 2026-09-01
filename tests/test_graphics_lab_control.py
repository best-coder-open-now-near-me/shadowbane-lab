from __future__ import annotations

import json
import mmap
import os
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.graphics_lab.control import (
    ADAPTIVE_OUTLINES,
    CONTROL_DESIRED_SEQUENCE_OFFSET,
    CONTROL_HEADER,
    CONTROL_PARAMETER_END,
    CONTROL_PARAMETER_OFFSET,
    CONTROL_STRUCTURE_SIZE,
    DEFAULT_PARAMETERS,
    GraphicsControlClient,
    GraphicsControlTarget,
    GraphicsParameters,
    discover_graphics_targets,
    pack_control_block,
    unpack_control_block,
)
from shadowbane_lab.graphics_lab.presets import GraphicsPresetStore


def _target(mapping_name: str = "Local\\WonderBaneGraphicsControl-test") -> GraphicsControlTarget:
    return GraphicsControlTarget(
        process_id=4321,
        process_creation_filetime_utc=0x1122334455667788,
        executable_path=Path("S:/WonderBane/sb.exe"),
        executable_sha256="a" * 64,
        mapping_name=mapping_name,
        status_path=Path("graphics-status.json"),
    )


def _assert_parameters_close(
    actual: GraphicsParameters, expected: GraphicsParameters
) -> None:
    assert actual.flags == expected.flags
    assert actual.dark_scene_outline == pytest.approx(expected.dark_scene_outline)
    assert actual.dark_scene_outline_strength == pytest.approx(
        expected.dark_scene_outline_strength
    )
    assert actual.bright_scene_ink_alpha == pytest.approx(
        expected.bright_scene_ink_alpha
    )
    assert actual.depth_edge_threshold == pytest.approx(expected.depth_edge_threshold)
    assert actual.band_thresholds == pytest.approx(expected.band_thresholds)
    for actual_color, expected_color in zip(
        actual.band_colors, expected.band_colors, strict=True
    ):
        assert actual_color == pytest.approx(expected_color)
    assert actual.vertex_tint_gamma == pytest.approx(expected.vertex_tint_gamma)
    assert actual.distant_highlight_compression == pytest.approx(
        expected.distant_highlight_compression
    )
    assert actual.feature_outline_width == pytest.approx(
        expected.feature_outline_width
    )


def test_control_abi_round_trips_exact_256_byte_layout() -> None:
    target = _target()
    assert DEFAULT_PARAMETERS.flags & ADAPTIVE_OUTLINES
    data = pack_control_block(target, DEFAULT_PARAMETERS)
    assert CONTROL_HEADER.size == CONTROL_STRUCTURE_SIZE == 256
    assert len(data) == 256
    snapshot = unpack_control_block(data, target)
    assert snapshot.desired_sequence == 2
    assert snapshot.applied_sequence == 2
    _assert_parameters_close(snapshot.parameters, DEFAULT_PARAMETERS)
    assert CONTROL_DESIRED_SEQUENCE_OFFSET == 24
    assert CONTROL_PARAMETER_OFFSET == 40
    assert CONTROL_PARAMETER_END == 140


def test_control_abi_clamps_float32_boundary_drift() -> None:
    target = _target()
    minimum = replace(DEFAULT_PARAMETERS, depth_edge_threshold=0.005)
    snapshot = unpack_control_block(pack_control_block(target, minimum), target)
    assert snapshot.parameters.depth_edge_threshold == 0.005


@pytest.mark.parametrize(
    "parameters",
    [
        replace(DEFAULT_PARAMETERS, flags=0x80000000),
        replace(DEFAULT_PARAMETERS, depth_edge_threshold=float("nan")),
        replace(DEFAULT_PARAMETERS, band_thresholds=(0.4, 0.3, 0.8)),
        replace(DEFAULT_PARAMETERS, dark_scene_outline_strength=1.1),
    ],
)
def test_parameters_reject_malformed_or_out_of_range_values(
    parameters: GraphicsParameters,
) -> None:
    with pytest.raises(ValueError):
        parameters.validate()


def test_discovers_only_status_with_live_controls(tmp_path: Path) -> None:
    root = tmp_path / "ShadowbaneLab" / "client-extension"
    root.mkdir(parents=True)
    status = {
        "producer_id": "wonderbane-extension.graphics",
        "process_identity": {
            "process_id": 4321,
            "process_creation_filetime_utc": 0x1122334455667788,
            "executable_path": "S:\\WonderBane\\sb.exe",
        },
        "executable_sha256": "a" * 64,
        "live_controls": {
            "available": True,
            "mapping_name": "Local\\WonderBaneGraphicsControl-4321-test",
        },
    }
    (root / "graphics-status-4321-test.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    targets = discover_graphics_targets(
        tmp_path, identity_validator=lambda target: target.process_id == 4321
    )
    assert len(targets) == 1
    assert targets[0].mapping_name.endswith("-4321-test")

    status["live_controls"]["available"] = False
    (root / "graphics-status-4321-test.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    assert discover_graphics_targets(tmp_path, identity_validator=lambda _: True) == ()


def test_preset_store_saves_and_loads_validated_parameters(tmp_path: Path) -> None:
    store = GraphicsPresetStore(tmp_path)
    adaptive = replace(
        DEFAULT_PARAMETERS,
        flags=DEFAULT_PARAMETERS.flags | ADAPTIVE_OUTLINES,
        dark_scene_outline_strength=0.36,
    )
    path = store.save("Dark lavender", adaptive)
    assert path.name == "Dark lavender.json"
    assert store.list_names() == ("Dark lavender",)
    assert store.load("Dark lavender") == adaptive
    with pytest.raises(ValueError):
        store.save("../escape", adaptive)


@pytest.mark.skipif(os.name != "nt", reason="named Windows mappings are Windows-only")
def test_named_mapping_write_uses_even_sequence_and_parameter_slice() -> None:
    mapping_name = f"Local\\WonderBaneGraphicsControl-test-{os.getpid()}"
    target = _target(mapping_name)
    with mmap.mmap(
        -1,
        CONTROL_STRUCTURE_SIZE,
        tagname=mapping_name,
        access=mmap.ACCESS_WRITE,
    ) as owner:
        owner[:] = pack_control_block(target, DEFAULT_PARAMETERS)
        adaptive = replace(
            DEFAULT_PARAMETERS,
            flags=DEFAULT_PARAMETERS.flags | ADAPTIVE_OUTLINES,
            dark_scene_outline_strength=0.41,
        )
        with GraphicsControlClient(target) as client:
            sequence = client.write(adaptive)
            assert sequence == 4
            snapshot = client.read()
            assert snapshot.desired_sequence == 4
            assert snapshot.applied_sequence == 2
            _assert_parameters_close(snapshot.parameters, adaptive)
        owner.seek(CONTROL_DESIRED_SEQUENCE_OFFSET)
        assert struct.unpack("<i", owner.read(4))[0] == 4


@pytest.mark.skipif(os.name != "nt", reason="named Windows mappings are Windows-only")
def test_named_mapping_can_restore_reviewed_baseline_from_invalid_parameters() -> None:
    mapping_name = f"Local\\WonderBaneGraphicsControl-repair-{os.getpid()}"
    target = _target(mapping_name)
    invalid = bytearray(pack_control_block(target, DEFAULT_PARAMETERS))
    depth_edge_threshold_offset = CONTROL_PARAMETER_OFFSET + 4 + (5 * 4)
    struct.pack_into("<f", invalid, depth_edge_threshold_offset, float("nan"))
    with mmap.mmap(
        -1,
        CONTROL_STRUCTURE_SIZE,
        tagname=mapping_name,
        access=mmap.ACCESS_WRITE,
    ) as owner:
        owner[:] = invalid
        with GraphicsControlClient(target) as client:
            with pytest.raises(ValueError, match="depth_edge_threshold"):
                client.read()
            sequence = client.restore_reviewed_baseline()
            assert sequence == 4
            snapshot = client.read()
            _assert_parameters_close(snapshot.parameters, DEFAULT_PARAMETERS)
            assert snapshot.desired_sequence == 4
            assert snapshot.applied_sequence == 2
