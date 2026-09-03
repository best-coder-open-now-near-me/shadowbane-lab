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
    if (planar.layer != DrawLayer::world_overlay
        || planar.reason != DrawClassificationReason::planar_overlay_state) {
        return Fail(L"perspective planar scene-overlay classification");
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
    // Preliminary world and overlays must not consume the final scene.
    AdvanceSceneFrame(&frame, world);
    for (const auto candidate : {ui, planar, ui}) {
        const auto decision = AdvanceSceneFrame(&frame, candidate);
        if (decision.composite_before_draw || decision.contributes_to_scene
            || frame.boundary_count != 0U) {
            return Fail(L"draw-state candidates cannot authorize capture");
        }
    }
    if (BeginReviewedSceneUiBoundary(&frame)) {
        return Fail(L"unreviewed or pre-clear boundary rejected");
    }
    frame.boundary_mapping_verified = true;
    if (BeginReviewedSceneUiBoundary(&frame)) {
        return Fail(L"preliminary world cannot arm main scene");
    }
    ObserveMainSceneClear(&frame);
    if (BeginReviewedSceneUiBoundary(&frame)) {
        return Fail(L"empty main scene rejected");
    }
    for (unsigned int draw = 0U; draw < 3417U; ++draw) {
        if (!AdvanceSceneFrame(&frame, world).contributes_to_scene) {
            return Fail(L"main-world draws remain eligible before boundary");
        }
        if (draw % 100U == 0U) {
            const auto decision = AdvanceSceneFrame(&frame, ui);
            if (decision.composite_before_draw || frame.boundary_count != 0U) {
                return Fail(L"mid-world orthographic draw cannot seal scene");
            }
        }
    }
    if (frame.main_scene_world_draw_count != 3417U
        || frame.world_draw_count != 3418U
        || frame.late_world_draw_count != 0U
        || !BeginReviewedSceneUiBoundary(&frame)
        || frame.accepted_boundary_draw_ordinal != frame.draw_count + 1U
        || frame.accepted_boundary_draw_ordinal <= frame.last_world_draw_ordinal
        || frame.composite_succeeded) {
        return Fail(L"complete main-world boundary independent of GPU outcome");
    }
    const auto candidates = frame.composite_candidate_count;
    AdvanceSceneFrame(&frame, ui);
    if (BeginReviewedSceneUiBoundary(&frame)
        || frame.composite_candidate_count != candidates
        || frame.boundary_count != 1U) {
        return Fail(L"no retry after UI starts even if composite failed");
    }
    const auto late = AdvanceSceneFrame(&frame, world);
    if (late.contributes_to_scene || frame.late_world_draw_count != 1U
        || frame.first_late_world_draw_ordinal != frame.draw_count) {
        return Fail(L"late geometry remains unmodified and counted");
    }
    if (frame.composite_candidate_count != frame.rejected_composite_candidate_count + 1U) {
        return Fail(L"bounded candidate journal");
    }
    frame = {};
    frame.boundary_mapping_verified = true;
    ObserveMainSceneClear(&frame);
    AdvanceSceneFrame(&frame, world);
    ObserveMainSceneClear(&frame);
    AdvanceSceneFrame(&frame, world);
    if (BeginReviewedSceneUiBoundary(&frame) || !frame.main_scene_invalidated) {
        return Fail(L"multiple main clears fail closed");
    }
    frame = {};
    frame.boundary_mapping_verified = true;
    ObserveMainSceneClear(&frame);
    AdvanceSceneFrame(&frame, world);
    frame.main_scene_invalidated = true;
    if (BeginReviewedSceneUiBoundary(&frame)) {
        return Fail(L"context change or intervening depth clear fails closed");
    }
    if (BeginReviewedSceneUiBoundary(nullptr)) {
        return Fail(L"null boundary rejected");
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
