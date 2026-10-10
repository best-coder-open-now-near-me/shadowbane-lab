import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "package_builder", Path(__file__).parents[1] / "scripts/build_navigation_inspector_package.py"
)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def results(tmp_path, status="run", failure=None, name=None):
    name = name or next(iter(builder.DIAGNOSTIC_TRANSPARENCY_FAILURES))
    suite = ET.Element("testsuite")
    case = ET.SubElement(suite, "testcase", name=name, status=status)
    if failure:
        ET.SubElement(case, failure)
    ET.SubElement(case, "system-out").text = "expected RGB differs from actual RGB"
    path = tmp_path / "native.xml"
    ET.ElementTree(suite).write(path)
    return path, {name}


def test_default_acceptance_rejects_known_transparency_failure(tmp_path):
    path, required = results(tmp_path, "fail", "failure")
    with pytest.raises(RuntimeError, match="failed"):
        builder.validate_native_results(path, required, diagnostic=False, exit_code=8)


def test_diagnostic_preserves_exact_known_failure(tmp_path):
    path, required = results(tmp_path, "fail", "failure")
    failures = builder.validate_native_results(path, required, diagnostic=True, exit_code=8)
    assert failures == [{"test": next(iter(required)), "status": "failed",
                         "detail": "expected RGB differs from actual RGB"}]


@pytest.mark.parametrize("case", ["unrelated", "skipped", "missing", "error", "duplicate", "exit"])
def test_diagnostic_cannot_bypass_other_gate_failures(tmp_path, case):
    path, required = results(tmp_path)
    suite = ET.parse(path).getroot()
    test = suite[0]
    code = 0
    if case == "unrelated":
        test.set("name", "runtime_lifetime")
        ET.SubElement(test, "failure")
        code = 8
    elif case in ("skipped", "error"):
        ET.SubElement(test, case)
    elif case == "missing":
        suite.remove(test)
    elif case == "duplicate":
        ET.SubElement(suite, "testcase", name=next(iter(required)), status="run")
    else:
        code = 8
    ET.ElementTree(suite).write(path)
    with pytest.raises(RuntimeError):
        builder.validate_native_results(path, required, diagnostic=True, exit_code=code)


@pytest.mark.parametrize("name", [
    "wonderbane_extension_selected_cue_runtime",
    "wonderbane_extension_selected_cue_native_material",
    "wonderbane_extension_effects_runtime",
])
@pytest.mark.parametrize("diagnostic", [False, True])
def test_required_runtime_failures_cannot_be_waived(tmp_path, name, diagnostic):
    path, required = results(tmp_path, "fail", "failure", name)
    with pytest.raises(RuntimeError, match="failed"):
        builder.validate_native_results(path, required, diagnostic=diagnostic, exit_code=8)


@pytest.mark.parametrize("profile_name", [
    "test_profile_configuration_crosses_real_native_channel_atomically",
    "test_real_cleanup_pending_preserves_owner_until_native_ack",
    "test_real_parent_cancel_preserves_pending_native_owner_until_cleanup_ack",
    "test_real_service_only_update_gap_preserves_exact_owner_and_cleanup",
])
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_profile_ipc_must_execute_once_and_pass(tmp_path, outcome, profile_name):
    assert profile_name in builder.REQUIRED_MOVEMENT_IPC_TESTS
    suite = ET.Element("testsuite")
    for name in builder.REQUIRED_MOVEMENT_IPC_TESTS:
        if name == profile_name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=name)
        if name == profile_name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=profile_name)
    path = tmp_path / "movement-ipc.xml"
    ET.ElementTree(suite).write(path)
    if outcome == "pass":
        builder.validate_movement_ipc_results(path, "test-profile")
    else:
        with pytest.raises(RuntimeError, match="required native movement IPC"):
            builder.validate_movement_ipc_results(path, "test-profile")


@pytest.mark.parametrize("name", sorted(builder.REQUIRED_TARGETED_ACTION_TESTS))
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_targeted_action_gates_must_execute_once(tmp_path, name, outcome):
    suite = ET.Element("testsuite")
    for required in builder.REQUIRED_TARGETED_ACTION_TESTS:
        if required == name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required, status="run")
        if required == name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=name, status="run")
    path = tmp_path / "targeted-action.xml"
    ET.ElementTree(suite).write(path)
    required = set(builder.REQUIRED_TARGETED_ACTION_TESTS)
    if outcome == "pass":
        assert builder.validate_native_results(path, required, diagnostic=False, exit_code=0) == []
    else:
        with pytest.raises(RuntimeError):
            builder.validate_native_results(path, required, diagnostic=False, exit_code=0)


@pytest.mark.parametrize(
    "name", sorted(builder.REQUIRED_VENDOR_TESTS | builder.REQUIRED_GUARD_TESTS
                   | builder.REQUIRED_CONDEMN_TESTS),
)
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_vendor_gates_must_execute_once(tmp_path, name, outcome):
    suite = ET.Element("testsuite")
    required_tests = (builder.REQUIRED_VENDOR_TESTS | builder.REQUIRED_GUARD_TESTS
                      | builder.REQUIRED_CONDEMN_TESTS)
    for required in required_tests:
        if required == name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required, status="run")
        if required == name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=name, status="run")
    path = tmp_path / "vendor.xml"
    ET.ElementTree(suite).write(path)
    required = set(required_tests)
    if outcome == "pass":
        assert builder.validate_native_results(path, required, diagnostic=False, exit_code=0) == []
    else:
        with pytest.raises(RuntimeError):
            builder.validate_native_results(path, required, diagnostic=False, exit_code=0)


def test_required_guard_gates_are_registered_native_tests():
    import re
    cmake = (Path(__file__).parents[1] / "native/wonderbane_extension/CMakeLists.txt").read_text(
        encoding="utf-8",
    )
    registered = set(re.findall(r"add_test\(NAME\s+(\w+)", cmake))
    assert builder.REQUIRED_GUARD_TESTS <= registered


def test_condemn_native_actions_are_a_required_package_gate():
    assert "wonderbane_extension_condemn_native" in builder.REQUIRED_CONDEMN_TESTS


def test_condemn_evidence_is_a_required_package_gate():
    assert "wonderbane_extension_condemn_evidence" in builder.REQUIRED_CONDEMN_TESTS


def test_condemn_controller_is_a_required_package_gate():
    assert "wonderbane_extension_condemn_controller" in builder.REQUIRED_CONDEMN_TESTS


def test_condemn_queue_and_owner_runtime_are_required_package_gates():
    assert {"wonderbane_extension_condemn_channel", "wonderbane_extension_condemn_runtime"} <= (
        builder.REQUIRED_CONDEMN_TESTS
    )


@pytest.mark.parametrize("diagnostic", [False, True])
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "duplicate"])
def test_object_combat_native_gates_cannot_be_omitted(tmp_path, diagnostic, outcome):
    required = set(builder.REQUIRED_COMBAT_TESTS)
    suite = ET.Element("testsuite")
    for name in sorted(required):
        ET.SubElement(suite, "testcase", name=name, status="run")
    if outcome == "missing":
        suite.remove(suite[0])
    elif outcome in ("skipped", "failure"):
        ET.SubElement(suite[0], outcome)
    elif outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=suite[0].get("name"), status="run")
    path = tmp_path / "combat.xml"
    ET.ElementTree(suite).write(path)
    if outcome == "pass":
        assert builder.validate_native_results(
            path, required, diagnostic=diagnostic, exit_code=0
        ) == []
    else:
        with pytest.raises(RuntimeError):
            builder.validate_native_results(path, required, diagnostic=diagnostic,
                                            exit_code=8 if outcome == "failure" else 0)


@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_combat_ipc_requires_real_execution(tmp_path, outcome):
    suite = ET.Element("testsuite")
    for name in sorted(builder.REQUIRED_COMBAT_IPC_TESTS):
        ET.SubElement(suite, "testcase", name=name)
    if outcome == "missing":
        suite.remove(suite[0])
    elif outcome in ("skipped", "failure", "error"):
        ET.SubElement(suite[0], outcome)
    elif outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=suite[0].get("name"))
    path = tmp_path / "combat-ipc.xml"
    ET.ElementTree(suite).write(path)
    if outcome == "pass":
        builder.validate_combat_ipc_results(path, "full")
    else:
        with pytest.raises(RuntimeError, match="combat IPC"):
            builder.validate_combat_ipc_results(path, "diagnostics-only")


def power_probe_steps(feature):
    return [
        {"name": f"{profile}-combat-power-{feature}-{suffix}", "exit_code": 0,
         "command": [f"wonderbane_extension_combat_power_{feature}_probe.exe", image]}
        for profile in ("full", "diagnostics-only")
        for suffix, image in (("binding", "official-13.exe"),
                              ("prepared-binding", f"{profile}-prepared-13.exe"))
    ]


@pytest.mark.parametrize("feature", ["initiation", "readiness", "movement", "special"])
def test_power_receipt_requires_all_four_executed_exact_image_gates(feature):
    validate = getattr(builder, f"validate_combat_power_{feature}_steps")
    assert validate(power_probe_steps(feature), reviewed_client=True)
    assert not validate([], reviewed_client=False)


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("failure", ["missing", "failed", "duplicate", "wrong_probe", "no_image"])
@pytest.mark.parametrize("feature", ["initiation", "readiness", "movement", "special"])
def test_power_receipt_cannot_certify_missing_or_wrong_execution(index, failure, feature):
    steps = power_probe_steps(feature)
    if failure == "missing":
        steps.pop(index)
    elif failure == "failed":
        steps[index]["exit_code"] = 1
    elif failure == "duplicate":
        steps.append(dict(steps[index]))
    elif failure == "wrong_probe":
        steps[index]["command"][0] = "other.exe"
    else:
        steps[index]["command"] = steps[index]["command"][:1]
    with pytest.raises(RuntimeError, match=feature):
        getattr(builder, f"validate_combat_power_{feature}_steps")(steps, reviewed_client=True)


@pytest.mark.parametrize("pair", [0, 2])
@pytest.mark.parametrize("feature", ["initiation", "readiness", "movement", "special"])
def test_power_gate_cannot_count_one_image_twice(pair, feature):
    steps = power_probe_steps(feature)
    steps[pair+1]["command"][1] = steps[pair]["command"][1]
    with pytest.raises(RuntimeError, match="original and prepared"):
        getattr(builder, f"validate_combat_power_{feature}_steps")(steps, reviewed_client=True)


@pytest.mark.parametrize("name", [
    *(f"wonderbane_extension_combat_power_image_{image}"
      for image in ("prepared12", "original12", "prepared13", "original13",
                   "prepared14", "original14", "unknown")),
    "wonderbane_extension_combat_image_prepared14",
    "wonderbane_extension_combat_image_original14",
    "wonderbane_extension_actor_effects_native_prepared14",
    "wonderbane_extension_movement_runtime_owner-service",
    "wonderbane_extension_movement_windows_input_mouse",
    "wonderbane_extension_combat_group_chat",
])
@pytest.mark.parametrize("failure", ["missing", "skipped", "failure", "duplicate"])
def test_native_combat_entry_and_ownership_are_required_gates(tmp_path, name, failure):
    assert name in builder.REQUIRED_COMBAT_TESTS
    suite = ET.Element("testsuite")
    for required in sorted(builder.REQUIRED_COMBAT_TESTS):
        if required == name and failure == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required, status="run")
        if required == name and failure in ("skipped", "failure"):
            ET.SubElement(case, failure)
        if required == name and failure == "duplicate":
            ET.SubElement(suite, "testcase", name=required, status="run")
    path = tmp_path / "admission.xml"
    ET.ElementTree(suite).write(path)
    with pytest.raises(RuntimeError):
        builder.validate_native_results(
            path, set(builder.REQUIRED_COMBAT_TESTS), diagnostic=False,
            exit_code=8 if failure == "failure" else 0,
        )


@pytest.mark.parametrize("profile", ["full", "diagnostics-only"])
@pytest.mark.parametrize("name", sorted(builder.REQUIRED_ACTOR_IPC_TESTS))
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_actor_ipc_requires_each_real_case_exactly_once(tmp_path, profile, name, outcome):
    suite = ET.Element("testsuite")
    for required in builder.REQUIRED_ACTOR_IPC_TESTS:
        if required == name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required)
        if required == name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
        if required == name and outcome == "duplicate":
            ET.SubElement(suite, "testcase", name=required)
    path = tmp_path / "actor-ipc.xml"
    ET.ElementTree(suite).write(path)
    if outcome == "pass":
        builder.validate_actor_ipc_results(path, profile)
    else:
        with pytest.raises(RuntimeError, match="actor IPC"):
            builder.validate_actor_ipc_results(path, profile)


def actor_probe_steps():
    return [
        {"name": f"{profile}-{feature}-{suffix}", "exit_code": 0,
         "command": [f"wonderbane_extension_{feature}_probe.exe", image]}
        for profile in ("full", "diagnostics-only")
        for feature in ("combat_item", "actor_effects_native",
                        "actor_inventory_native", "actor_buff_observation")
        for suffix, image in (("binding", "official-13.exe"),
                              ("prepared-binding", f"{profile}-prepared-13.exe"))
    ]


def test_actor_probe_gates_require_both_images_and_both_profiles():
    assert builder.validate_actor_probe_steps(actor_probe_steps(), reviewed_client=True)
    assert not builder.validate_actor_probe_steps([], reviewed_client=False)


@pytest.mark.parametrize("index", range(16))
@pytest.mark.parametrize("failure", ["missing", "failed", "duplicate", "wrong_binary",
                                    "missing_command", "not_list", "no_image", "extra_argument",
                                    "empty_image", "nonstring_image"])
def test_actor_probe_gate_rejects_missing_malformed_or_wrong_execution(index, failure):
    steps = actor_probe_steps()
    if failure == "missing":
        steps.pop(index)
    elif failure == "failed":
        steps[index]["exit_code"] = 1
    elif failure == "duplicate":
        steps.append(dict(steps[index]))
    elif failure == "wrong_binary":
        steps[index]["command"][0] = "wonderbane_extension_other_probe.exe"
    elif failure == "missing_command":
        del steps[index]["command"]
    elif failure == "not_list":
        steps[index]["command"] = "probe.exe official-13.exe"
    elif failure == "no_image":
        steps[index]["command"].pop()
    elif failure == "extra_argument":
        steps[index]["command"].append("extra")
    elif failure == "empty_image":
        steps[index]["command"][1] = ""
    else:
        steps[index]["command"][1] = 13
    with pytest.raises(RuntimeError, match="actor probe"):
        builder.validate_actor_probe_steps(steps, reviewed_client=True)


@pytest.mark.parametrize("pair", range(0, 16, 2))
def test_actor_probe_cannot_count_same_image_twice(pair):
    steps = actor_probe_steps()
    steps[pair + 1]["command"][1] = steps[pair]["command"][1]
    with pytest.raises(RuntimeError, match="original and prepared"):
        builder.validate_actor_probe_steps(steps, reviewed_client=True)


def item_trace_steps():
    return [{"name": f"{profile}-item_application_trace-{suffix}", "exit_code": 0,
             "command": ["wonderbane_extension_item_application_trace_probe.exe", image]}
            for profile in ("full", "diagnostics-only")
            for suffix, image in (("binding", "original14.exe"),
                                  ("prepared-binding", f"{profile}-prepared14.exe"))]


def test_item_trace_probe_requires_both_images_and_profiles():
    assert builder.validate_item_trace_probe_steps(item_trace_steps(), reviewed_client=True)
    assert not builder.validate_item_trace_probe_steps([], reviewed_client=False)
    assert len(builder.REQUIRED_ITEM_TRACE_TESTS) == 7


def activation_steps():
    return [{"name": f"{profile}-{feature}-{suffix}", "exit_code": 0,
             "command": [f"wonderbane_extension_{feature}_{binary}.exe", image]}
            for profile in ("full", "diagnostics-only")
            for feature, binary in (("combat_activation_incoming", "probe"),
                                    ("combat_activation_completion", "probe"),
                                    ("combat_activation_observer", "test"))
            for suffix, image in (("binding", "original15.exe"),
                                  ("prepared-binding", f"{profile}-prepared15.exe"))]


def test_activation_boundaries_require_both_images_and_profiles():
    assert builder.validate_activation_probe_steps(activation_steps(), reviewed_client=True)
    assert not builder.validate_activation_probe_steps([], reviewed_client=False)
    assert "wonderbane_extension_combat_activation_observer" in builder.REQUIRED_COMBAT_TESTS


@pytest.mark.parametrize("index", range(12))
@pytest.mark.parametrize("failure", ["missing", "failed", "duplicate",
                                    "wrong_binary", "same_image"])
def test_activation_boundary_gate_rejects_unqualified_execution(index, failure):
    steps = activation_steps()
    if failure == "missing":
        steps.pop(index)
    elif failure == "failed":
        steps[index]["exit_code"] = 1
    elif failure == "duplicate":
        steps.append(dict(steps[index]))
    elif failure == "wrong_binary":
        steps[index]["command"][0] = "other.exe"
    else:
        steps[index]["command"][1] = steps[index ^ 1]["command"][1]
    with pytest.raises(RuntimeError):
        builder.validate_activation_probe_steps(steps, reviewed_client=True)


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("failure", ["missing", "failed", "duplicate",
                                    "wrong_binary", "same_image"])
def test_item_trace_gate_cannot_certify_missing_or_wrong_probe(index, failure):
    steps = item_trace_steps()
    if failure == "missing":
        steps.pop(index)
    elif failure == "failed":
        steps[index]["exit_code"] = 1
    elif failure == "duplicate":
        steps.append(dict(steps[index]))
    elif failure == "wrong_binary":
        steps[index]["command"][0] = "other.exe"
    else:
        steps[index]["command"][1] = steps[index ^ 1]["command"][1]
    with pytest.raises(RuntimeError):
        builder.validate_item_trace_probe_steps(steps, reviewed_client=True)


@pytest.mark.parametrize("name", sorted(builder.REQUIRED_GRAPHICS_TESTS))
@pytest.mark.parametrize("diagnostic", [False, True])
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "duplicate"])
def test_preserved_graphics_native_gate_cannot_be_waived(tmp_path, name, diagnostic, outcome):
    suite = ET.Element("testsuite")
    for required in builder.REQUIRED_GRAPHICS_TESTS:
        if required == name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required, status="run")
        if required == name and outcome in ("skipped", "failure"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=name, status="run")
    path = tmp_path / "graphics.xml"
    ET.ElementTree(suite).write(path)
    if outcome == "pass":
        assert builder.validate_native_results(
            path, builder.REQUIRED_GRAPHICS_TESTS, diagnostic=diagnostic, exit_code=0
        ) == []
    else:
        with pytest.raises(RuntimeError):
            builder.validate_native_results(
                path, builder.REQUIRED_GRAPHICS_TESTS, diagnostic=diagnostic,
                exit_code=8 if outcome == "failure" else 0,
            )


def graphics_distribution_members():
    wheel = [f"shadowbane_lab/{name}" for name in builder.GRAPHICS_HOST_MODULES]
    source = [f"package/src/{name}" for name in wheel]
    source.extend(f"package/native/wonderbane_extension/{Path(name).stem}{suffix}"
                  for name in builder.GRAPHICS_NATIVE_CONTRACTS
                  for suffix in (".cpp", ".h", "_test.cpp"))
    return wheel, source


def test_composed_graphics_distribution_complete():
    wheel, source = graphics_distribution_members()
    builder.validate_graphics_wheel_members(wheel)
    builder.validate_graphics_source_members(source)


@pytest.mark.parametrize("missing", graphics_distribution_members()[0])
def test_composed_wheel_rejects_missing_graphics_module(missing):
    wheel, _ = graphics_distribution_members()
    wheel.remove(missing)
    with pytest.raises(RuntimeError, match="missing preserved graphics"):
        builder.validate_graphics_wheel_members(wheel)


@pytest.mark.parametrize("missing", graphics_distribution_members()[1])
def test_composed_sdist_rejects_missing_graphics_source(missing):
    _, source = graphics_distribution_members()
    source.remove(missing)
    with pytest.raises(RuntimeError, match="missing preserved graphics"):
        builder.validate_graphics_source_members(source)


@pytest.mark.parametrize("profile", ["full", "diagnostics-only"])
def test_pretracking_actor_gate_set_cannot_qualify_new_package(tmp_path, profile):
    # Fixed historical set intentionally does not derive from the current required set.
    suite = ET.Element("testsuite")
    for name in (
        "test_real_preparation_service_ipc_keeps_passive_ownership_and_manual_activity",
        "test_real_windows_parent_and_child_native_consumer",
        "test_real_native_publication_mapping_roundtrip",
    ):
        ET.SubElement(suite, "testcase", name=name)
    path = tmp_path / "old-actor-ipc.xml"
    ET.ElementTree(suite).write(path)
    with pytest.raises(RuntimeError, match="actor IPC"):
        builder.validate_actor_ipc_results(path, profile)
    ET.SubElement(suite, "testcase", name="test_real_native_tracking_frame_roundtrip")
    ET.ElementTree(suite).write(path)
    with pytest.raises(RuntimeError, match="actor IPC"):
        builder.validate_actor_ipc_results(path, profile)
    ET.SubElement(suite, "testcase", name="test_real_native_group_chat_wire_roundtrip")
    ET.ElementTree(suite).write(path)
    builder.validate_actor_ipc_results(path, profile)


def test_tracking_native_response_and_install_failure_modes_are_required():
    assert {
        "wonderbane_extension_tracking_responses",
        "wonderbane_extension_tracking_install_failure_1",
        "wonderbane_extension_tracking_install_failure_2",
        "wonderbane_extension_tracking_install_failure_3",
    } <= builder.REQUIRED_COMBAT_TESTS


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("failure", [None, "missing", "failed", "duplicate",
                                    "wrong_binary", "same_image"])
def test_group_chat_probe_requires_both_images_per_profile(index, failure):
    steps = [
        {"name": f"{profile}-combat_group_chat-{suffix}", "exit_code": 0,
         "command": ["wonderbane_extension_combat_group_chat_probe.exe", image]}
        for profile in ("full", "diagnostics-only")
        for suffix, image in (("binding", "official.exe"), ("prepared-binding", "prepared.exe"))
    ]
    if failure == "missing":
        steps.pop(index)
    elif failure == "failed":
        steps[index]["exit_code"] = 1
    elif failure == "duplicate":
        steps.append(dict(steps[index]))
    elif failure == "wrong_binary":
        steps[index]["command"][0] = "other.exe"
    elif failure == "same_image":
        steps[index]["command"][1] = steps[index ^ 1]["command"][1]
    if failure is None:
        assert builder.validate_group_chat_probe_steps(steps, reviewed_client=True)
    else:
        with pytest.raises(RuntimeError):
            builder.validate_group_chat_probe_steps(steps, reviewed_client=True)
