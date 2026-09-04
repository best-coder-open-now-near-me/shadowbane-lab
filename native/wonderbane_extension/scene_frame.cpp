#include "scene_frame.h"

namespace wonderbane::extension {

DrawClassification ClassifyFixedFunctionDraw(
    const FixedFunctionDrawState& state
) noexcept {
    if (state.projection == DrawProjection::unknown) {
        return {
            DrawLayer::unknown,
            DrawClassificationReason::projection_unavailable,
        };
    }
    if (state.projection == DrawProjection::orthographic) {
        return {
            DrawLayer::ui_overlay,
            DrawClassificationReason::orthographic_projection,
        };
    }
    if (state.planar_overlay_candidate
        && state.texture_enabled
        && (state.alpha_test_enabled || state.blend_enabled)
        && !state.lighting_enabled
        && !state.fog_enabled) {
        return {
            DrawLayer::world_overlay,
            DrawClassificationReason::planar_overlay_state,
        };
    }
    if (state.blend_enabled) {
        return {
            DrawLayer::world_translucent,
            DrawClassificationReason::blended_perspective,
        };
    }
    if (state.depth_writes && state.alpha_test_enabled) {
        return {
            DrawLayer::world_alpha_tested,
            DrawClassificationReason::depth_writing_alpha_tested,
        };
    }
    if (state.depth_writes) {
        return {
            DrawLayer::world_opaque,
            DrawClassificationReason::depth_writing_opaque,
        };
    }
    return {
        DrawLayer::world_overlay,
        DrawClassificationReason::depthless_perspective,
    };
}

bool IsWorldLayer(const DrawLayer layer) noexcept {
    return layer == DrawLayer::world_opaque
        || layer == DrawLayer::world_alpha_tested
        || layer == DrawLayer::world_translucent
        || layer == DrawLayer::world_overlay;
}

bool IsUiLayer(const DrawLayer layer) noexcept {
    return layer == DrawLayer::ui_overlay;
}

bool IsSceneCompositeCandidate(
    const DrawClassification& classification
) noexcept {
    return classification.reason
            == DrawClassificationReason::orthographic_projection
        || classification.reason
            == DrawClassificationReason::planar_overlay_state;
}

const char* DrawLayerName(const DrawLayer layer) noexcept {
    switch (layer) {
        case DrawLayer::unknown:
            return "unknown";
        case DrawLayer::world_opaque:
            return "world-opaque";
        case DrawLayer::world_alpha_tested:
            return "world-alpha-tested";
        case DrawLayer::world_translucent:
            return "world-translucent";
        case DrawLayer::world_overlay:
            return "world-overlay";
        case DrawLayer::ui_overlay:
            return "ui-overlay";
        case DrawLayer::count:
            break;
    }
    return "invalid";
}

const char* DrawClassificationReasonName(
    const DrawClassificationReason reason
) noexcept {
    switch (reason) {
        case DrawClassificationReason::projection_unavailable:
            return "projection-unavailable";
        case DrawClassificationReason::orthographic_projection:
            return "orthographic-projection";
        case DrawClassificationReason::planar_overlay_state:
            return "planar-overlay-state";
        case DrawClassificationReason::depth_writing_opaque:
            return "depth-writing-opaque";
        case DrawClassificationReason::depth_writing_alpha_tested:
            return "depth-writing-alpha-tested";
        case DrawClassificationReason::blended_perspective:
            return "blended-perspective";
        case DrawClassificationReason::depthless_perspective:
            return "depthless-perspective";
        case DrawClassificationReason::count:
            break;
    }
    return "invalid";
}

SceneFrameDecision AdvanceSceneFrame(
    SceneFrameState* const frame,
    const DrawClassification& classification
) noexcept {
    SceneFrameDecision decision{};
    decision.classification = classification;
    if (frame == nullptr) {
        return decision;
    }
    ++frame->draw_count;
    const std::size_t layer_index = static_cast<std::size_t>(classification.layer);
    if (layer_index < frame->draw_counts.size()) {
        ++frame->draw_counts[layer_index];
    }
    const std::size_t reason_index = static_cast<std::size_t>(
        classification.reason
    );
    if (reason_index < frame->reason_counts.size()) {
        ++frame->reason_counts[reason_index];
    }
    if (IsSceneCompositeCandidate(classification) && !frame->composite_requested) {
        // Shape/state candidates are diagnostic only. Even an armed depth pass
        // cannot prove that the main world has finished (1.6.8 regression).
        ++frame->composite_candidate_count;
        ++frame->rejected_composite_candidate_count;
        if (frame->first_composite_candidate_draw_ordinal == 0U) {
            frame->first_composite_candidate_draw_ordinal = frame->draw_count;
        }
    }
    if (classification.reason == DrawClassificationReason::planar_overlay_state) {
        // Preserve the separate planar-overlay effect policy, not phase authority.
        return decision;
    }
    if (IsWorldLayer(classification.layer)) {
        ++frame->world_draw_count;
        if (frame->first_world_draw_ordinal == 0U) {
            frame->first_world_draw_ordinal = frame->draw_count;
        }
        frame->last_world_draw_ordinal = frame->draw_count;
        if (frame->phase == SceneFramePhase::ui) {
            ++frame->late_world_draw_count;
            if (frame->first_late_world_draw_ordinal == 0U) {
                frame->first_late_world_draw_ordinal = frame->draw_count;
            }
            return decision;
        }
        decision.contributes_to_scene = true;
        if (frame->main_scene_start_count == 1U) {
            ++frame->main_scene_world_draw_count;
        }
        frame->phase = SceneFramePhase::world;
        return decision;
    }
    return decision;
}

void ObserveMainSceneClear(SceneFrameState* const frame) noexcept {
    if (frame == nullptr) {
        return;
    }
    ++frame->main_scene_start_count;
    frame->main_scene_world_draw_count = 0U;
    if (frame->composite_requested || frame->main_scene_start_count != 1U) {
        frame->main_scene_invalidated = true;
    }
}

bool BeginReviewedSceneUiBoundary(SceneFrameState* const frame) noexcept {
    if (frame == nullptr || !frame->boundary_mapping_verified
        || frame->composite_requested || frame->main_scene_invalidated
        || frame->main_scene_start_count != 1U
        || frame->main_scene_world_draw_count == 0U) {
        return false;
    }
    ++frame->composite_candidate_count;
    if (frame->first_composite_candidate_draw_ordinal == 0U) {
        frame->first_composite_candidate_draw_ordinal = frame->draw_count + 1U;
    }
    frame->composite_requested = true;
    ++frame->boundary_count;
    // Signal occurs between draws: identify the next draw, even for a hidden UI.
    frame->accepted_boundary_draw_ordinal = frame->draw_count + 1U;
    frame->phase = SceneFramePhase::ui;
    return true;
}

}  // namespace wonderbane::extension
