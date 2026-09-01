#include "graphics_status.h"
#include "graphics_control.h"
#include "scene_frame.h"

#include <Windows.h>

#include <array>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>

namespace {

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

}  // namespace

int wmain() {
    using wonderbane::extension::BuildGraphicsCameraState;
    using wonderbane::extension::ConfigureGraphicsPresentEntry;
    using wonderbane::extension::GetGraphicsStatusPath;
    using wonderbane::extension::GraphicsCameraState;
    using wonderbane::extension::HasGraphicsExtensionToken;
    using wonderbane::extension::IsGraphicsVersionAtLeast;
    using wonderbane::extension::ObserveGraphicsCameraState;
    using wonderbane::extension::ObserveGraphicsPresent;
    using wonderbane::extension::ReportDepthEdgePassComposite;
    using wonderbane::extension::ReportSceneColorCapture;
    using wonderbane::extension::ReportSceneFrameClassification;
    using wonderbane::extension::SceneFramePhase;
    using wonderbane::extension::SceneFrameState;
    using wonderbane::extension::StartGraphicsControl;
    using wonderbane::extension::StartGraphicsStatusPublication;
    using wonderbane::extension::StopGraphicsControl;
    using wonderbane::extension::StopGraphicsStatusPublication;

    constexpr char extensions[] =
        "GL_ARB_depth_texture GL_EXT_framebuffer_object GL_EXT_texture3D";
    if (!HasGraphicsExtensionToken(extensions, "GL_ARB_depth_texture")
        || !HasGraphicsExtensionToken(extensions, "GL_EXT_framebuffer_object")
        || HasGraphicsExtensionToken(extensions, "GL_EXT_framebuffer")
        || HasGraphicsExtensionToken(extensions, "")) {
        return Fail(L"extension token matching");
    }
    if (!IsGraphicsVersionAtLeast("2.1.0 fixture", 1U, 4U)
        || !IsGraphicsVersionAtLeast("1.4 fixture", 1U, 4U)
        || IsGraphicsVersionAtLeast("1.3 fixture", 1U, 4U)
        || IsGraphicsVersionAtLeast("vendor", 1U, 0U)) {
        return Fail(L"graphics version parsing");
    }
    DWORD result = StartGraphicsStatusPublication();
    if (result != ERROR_SUCCESS) {
        return Fail(L"status publisher startup");
    }
    result = StartGraphicsControl();
    if (result != ERROR_SUCCESS) {
        StopGraphicsStatusPublication();
        return Fail(L"graphics control startup");
    }
    result = ConfigureGraphicsPresentEntry(
        "GDI32.dll",
        "SwapBuffers",
        23'789'964U,
        "diagnostics-only"
    );
    if (result != ERROR_SUCCESS) {
        StopGraphicsControl();
        StopGraphicsStatusPublication();
        return Fail(L"present entry configuration");
    }
    constexpr std::array<float, 16U> view{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, 1.0F, 0.0F,
        -1.0F, -2.0F, -3.0F, 1.0F,
    };
    constexpr std::array<float, 16U> projection{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, -1.0F, -1.0F,
        0.0F, 0.0F, -0.2F, 0.0F,
    };
    constexpr std::array<int, 4U> viewport{0, 0, 1280, 720};
    GraphicsCameraState camera{};
    if (!BuildGraphicsCameraState(
            view.data(),
            view.size(),
            projection.data(),
            projection.size(),
            viewport.data(),
            viewport.size(),
            &camera
        )
        || std::fabs(camera.position[0] - 1.0F) > 0.001F
        || std::fabs(camera.position[1] - 2.0F) > 0.001F
        || std::fabs(camera.position[2] - 3.0F) > 0.001F
        || std::fabs(camera.forward[2] + 1.0F) > 0.001F
        || std::fabs(camera.up[1] - 1.0F) > 0.001F
        || std::fabs(camera.zoom - 1.0F) > 0.001F
        || std::fabs(camera.vertical_fov_degrees - 90.0F) > 0.001F) {
        StopGraphicsControl();
        StopGraphicsStatusPublication();
        return Fail(L"camera state derivation");
    }
    std::array<float, 16U> invalid_view = view;
    invalid_view[0] = 2.0F;
    if (BuildGraphicsCameraState(
            invalid_view.data(), invalid_view.size(),
            projection.data(), projection.size(),
            viewport.data(), viewport.size(), &camera
        )) {
        StopGraphicsControl();
        StopGraphicsStatusPublication();
        return Fail(L"invalid camera state rejection");
    }
    ObserveGraphicsCameraState(
        view.data(), view.size(), projection.data(), projection.size(),
        viewport.data(), viewport.size(), 2
    );
    ObserveGraphicsCameraState(
        view.data(), view.size(), projection.data(), projection.size(),
        viewport.data(), viewport.size(), 1
    );
    ObserveGraphicsPresent();
    ReportDepthEdgePassComposite();
    ReportSceneColorCapture();
    SceneFrameState classified_frame{};
    classified_frame.phase = SceneFramePhase::ui;
    classified_frame.draw_counts[1] = 3U;
    classified_frame.draw_counts[5] = 2U;
    classified_frame.reason_counts[1] = 2U;
    classified_frame.reason_counts[3] = 3U;
    classified_frame.draw_count = 5U;
    classified_frame.world_draw_count = 3U;
    classified_frame.boundary_count = 1U;
    classified_frame.late_world_draw_count = 1U;
    classified_frame.composite_candidate_count = 2U;
    classified_frame.rejected_composite_candidate_count = 1U;
    classified_frame.first_world_draw_ordinal = 1U;
    classified_frame.first_composite_candidate_draw_ordinal = 3U;
    classified_frame.accepted_boundary_draw_ordinal = 4U;
    classified_frame.first_late_world_draw_ordinal = 5U;
    classified_frame.last_world_draw_ordinal = 5U;
    classified_frame.fixed_function_refresh_count = 1U;
    ReportSceneFrameClassification(classified_frame);
    std::array<wchar_t, 1024U> path{};
    result = GetGraphicsStatusPath(path.data(), path.size());
    if (result != ERROR_SUCCESS || path[0] == L'\0') {
        StopGraphicsControl();
        StopGraphicsStatusPublication();
        return Fail(L"status path");
    }
    bool observed = false;
    std::string json{};
    for (DWORD poll = 0U; poll < 100U; ++poll) {
        std::ifstream stream(std::filesystem::path(path.data()), std::ios::binary);
        if (stream) {
            json.assign(
                std::istreambuf_iterator<char>(stream),
                std::istreambuf_iterator<char>()
            );
            stream.close();
            if (json.find("\"call_count\":1") != std::string::npos
                && json.find("\"state\":\"active\"") != std::string::npos) {
                observed = true;
                break;
            }
        }
        Sleep(20U);
    }
    ObserveGraphicsCameraState(
        view.data(), view.size(), projection.data(), projection.size(),
        viewport.data(), viewport.size(), 1
    );
    Sleep(2U);
    ObserveGraphicsPresent();
    ObserveGraphicsCameraState(
        view.data(), view.size(), projection.data(), projection.size(),
        viewport.data(), viewport.size(), 1
    );
    Sleep(2U);
    ObserveGraphicsPresent();
    std::array<float, 16U> conflicting_view = view;
    conflicting_view[12] = -9.0F;
    ObserveGraphicsCameraState(
        view.data(), view.size(), projection.data(), projection.size(),
        viewport.data(), viewport.size(), 1
    );
    ObserveGraphicsCameraState(
        conflicting_view.data(), conflicting_view.size(),
        projection.data(), projection.size(), viewport.data(), viewport.size(), 1
    );
    ObserveGraphicsPresent();
    StopGraphicsStatusPublication();
    StopGraphicsControl();
    {
        std::ifstream stream(std::filesystem::path(path.data()), std::ios::binary);
        if (stream) {
            json.assign(
                std::istreambuf_iterator<char>(stream),
                std::istreambuf_iterator<char>()
            );
        }
    }
    DeleteFileW(path.data());
    if (!observed
        || json.find("\"producer_id\":\"wonderbane-extension.graphics\"")
            == std::string::npos
        || json.find("\"schema_version\":2") == std::string::npos
        || json.find("\"runtime_profile\":\"diagnostics-only\"")
            == std::string::npos
        || json.find("\"call_count\":4") == std::string::npos
        || json.find("\"clock\":\"windows-query-performance-counter\"")
            == std::string::npos
        || json.find("\"sample_count\":3") == std::string::npos
        || json.find("\"samples\":[[1,") == std::string::npos
        || json.find("\"camera_state\":{\"schema_version\":1")
            == std::string::npos
        || json.find("\"source\":\"first-perspective-depth-writing-world-draw\"")
            != std::string::npos
        || json.find(
            "\"source\":\"unique-base-model-view-per-present\""
        ) == std::string::npos
        || json.find("\"mapping_authority\":"
            "\"runtime-observed-fixed-function-state\"") == std::string::npos
        || json.find("\"latest_sample_sequence\":3") == std::string::npos
        || json.find("\"producer_drop_count\":1") == std::string::npos
        || json.find("\"position\":[1,2,3]") == std::string::npos
        || json.find("\"vertical_fov_degrees\":90") == std::string::npos
        || json.find("\"viewport\":[0,0,1280,720]") == std::string::npos
        || json.find("\"iat_rva\":23789964") == std::string::npos
        || json.find("\"executable_sha256\":\"") == std::string::npos
        || json.find("\"context_observed\":false") == std::string::npos
        || json.find("\"composite_count\":1") == std::string::npos
        || json.find("\"radius_pixels\":1.0") == std::string::npos
        || json.find("\"edge_metric\":\"single-owner-inverse-depth-curvature\"")
            == std::string::npos
        || json.find("\"sample_kernel\":\"cardinal-five-sample\"")
            == std::string::npos
        || json.find("\"scene_color_capture\":{\"schema_version\":1,"
            "\"state\":\"active\"")
            == std::string::npos
        || json.find("\"capture_count\":1") == std::string::npos
        || json.find("\"transport\":\"gpu-to-gpu\"") == std::string::npos
        || json.find("\"cpu_readback\":false") == std::string::npos
        || json.find("\"draw_classification\":{\"schema_version\":1,"
            "\"state\":\"active\"")
            == std::string::npos
        || json.find("\"latest\":{\"phase\":\"ui\"") == std::string::npos
        || json.find("\"world_opaque\":3") == std::string::npos
        || json.find("\"orthographic_projection\":2") == std::string::npos
        || json.find("\"draw_count\":5") == std::string::npos
        || json.find("\"world_draw_count\":3") == std::string::npos
        || json.find("\"composite_candidate_count\":2")
            == std::string::npos
        || json.find("\"rejected_composite_candidate_count\":1")
            == std::string::npos
        || json.find("\"first_world_draw_ordinal\":1")
            == std::string::npos
        || json.find("\"first_composite_candidate_draw_ordinal\":3")
            == std::string::npos
        || json.find("\"accepted_boundary_draw_ordinal\":4")
            == std::string::npos
        || json.find("\"first_late_world_draw_ordinal\":5")
            == std::string::npos
        || json.find("\"last_world_draw_ordinal\":5")
            == std::string::npos
        || json.find("\"fixed_function_refresh_count\":1")
            == std::string::npos
        || json.find("\"fixed_function_state\":\"cached-with-transition-hooks\"")
            == std::string::npos
        || json.find("\"maximum_ordinary_frame_refreshes\":1")
            == std::string::npos
        || json.find(
            "\"boundary_ownership\":\"depth-pass-armed-idempotent\""
        ) == std::string::npos
        || json.find(
            "\"candidate_retry\":\"until-depth-pass-accepts\""
        ) == std::string::npos
        || json.find(
            "\"planar_overlay\":"
            "\"excluded-and-retryable-composite-candidate\""
        ) == std::string::npos
        || json.find(
            "\"late_world_after_ui\":\"effect-eligible-and-counted\""
        )
            == std::string::npos
        || json.find("\"live_controls\":{\"available\":true")
            == std::string::npos
        || json.find("\"mapping_name\":\"Local\\\\WonderBaneGraphicsControl-")
            == std::string::npos
        || json.find("\"desired_sequence\":2,\"applied_sequence\":2")
            == std::string::npos) {
        ::fprintf(stderr, "status JSON: %s\n", json.c_str());
        return Fail(L"published status JSON");
    }
    return 0;
}
