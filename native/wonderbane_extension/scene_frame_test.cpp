#include "scene_frame.h"

#include <cstdio>
#include <cstring>

namespace {

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

}  // namespace

int wmain() {
    using namespace wonderbane::extension;

    FixedFunctionDrawState state{};
    if (ClassifyFixedFunctionDraw(state).layer != DrawLayer::unknown) {
        return Fail(L"unknown projection classification");
    }
    state.projection = DrawProjection::orthographic;
    if (ClassifyFixedFunctionDraw(state).layer != DrawLayer::ui_overlay) {
        return Fail(L"orthographic UI classification");
    }
    state.projection = DrawProjection::perspective;
    state.depth_writes = true;
    if (ClassifyFixedFunctionDraw(state).layer != DrawLayer::world_opaque) {
        return Fail(L"opaque world classification");
    }
    state.alpha_test_enabled = true;
    if (ClassifyFixedFunctionDraw(state).layer != DrawLayer::world_alpha_tested) {
        return Fail(L"alpha-tested world classification");
    }
    state.blend_enabled = true;
    if (ClassifyFixedFunctionDraw(state).layer != DrawLayer::world_translucent) {
        return Fail(L"translucent world classification");
    }
    state.planar_overlay_candidate = true;
    state.texture_enabled = true;
    state.lighting_enabled = false;
    state.fog_enabled = false;
    const DrawClassification planar = ClassifyFixedFunctionDraw(state);
    if (planar.layer != DrawLayer::ui_overlay
        || planar.reason != DrawClassificationReason::planar_overlay_state) {
        return Fail(L"perspective planar UI classification");
    }
    state.planar_overlay_candidate = false;
    state.blend_enabled = false;
    state.alpha_test_enabled = false;
    state.depth_writes = false;
    if (ClassifyFixedFunctionDraw(state).layer != DrawLayer::world_overlay) {
        return Fail(L"depthless perspective classification");
    }

    SceneFrameState frame{};
    if (frame.fixed_function_refresh_count != 0U) {
        return Fail(L"new frame has fixed-function refreshes");
    }
    const DrawClassification world{
        DrawLayer::world_opaque,
        DrawClassificationReason::depth_writing_opaque,
    };
    const DrawClassification ui{
        DrawLayer::ui_overlay,
        DrawClassificationReason::orthographic_projection,
    };
    SceneFrameDecision decision = AdvanceSceneFrame(&frame, ui);
    if (decision.contributes_to_scene || decision.composite_before_draw
        || frame.phase != SceneFramePhase::awaiting_world
        || frame.boundary_count != 0U) {
        return Fail(L"pre-world UI does not seal frame");
    }
    decision = AdvanceSceneFrame(&frame, world);
    if (!decision.contributes_to_scene || decision.composite_before_draw
        || frame.phase != SceneFramePhase::world) {
        return Fail(L"world frame transition");
    }
    decision = AdvanceSceneFrame(&frame, ui);
    if (decision.contributes_to_scene || !decision.composite_before_draw
        || frame.phase != SceneFramePhase::ui
        || frame.boundary_count != 1U) {
        return Fail(L"single pre-UI boundary");
    }
    decision = AdvanceSceneFrame(&frame, ui);
    if (decision.composite_before_draw || frame.boundary_count != 1U) {
        return Fail(L"duplicate UI boundary rejection");
    }
    decision = AdvanceSceneFrame(&frame, world);
    if (!decision.contributes_to_scene || decision.composite_before_draw
        || frame.late_world_draw_count != 1U) {
        return Fail(L"late world draw remains effect eligible");
    }
    if (frame.draw_counts[static_cast<std::size_t>(DrawLayer::world_opaque)] != 2U
        || frame.draw_counts[static_cast<std::size_t>(DrawLayer::ui_overlay)] != 3U) {
        return Fail(L"bounded layer counters");
    }
    if (frame.reason_counts[static_cast<std::size_t>(
            DrawClassificationReason::depth_writing_opaque
        )] != 2U
        || frame.reason_counts[static_cast<std::size_t>(
            DrawClassificationReason::orthographic_projection
        )] != 3U) {
        return Fail(L"bounded reason counters");
    }
    if (std::strcmp(DrawLayerName(DrawLayer::world_opaque), "world-opaque") != 0
        || std::strcmp(
            DrawClassificationReasonName(
                DrawClassificationReason::orthographic_projection
            ),
            "orthographic-projection"
        ) != 0) {
        return Fail(L"diagnostic names");
    }
    return 0;
}
