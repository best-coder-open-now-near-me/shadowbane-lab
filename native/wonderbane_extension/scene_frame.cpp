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
    if (classification.reason == DrawClassificationReason::planar_overlay_state) {
        // Perspective planar overlays are excluded from cel processing, but live
        // WonderBane frames place one before the body of the world. It is not a
        // trustworthy world-to-UI boundary; the later orthographic transition is.
        return decision;
    }
    if (IsWorldLayer(classification.layer)) {
        decision.contributes_to_scene = true;
        if (frame->phase == SceneFramePhase::ui) {
            ++frame->late_world_draw_count;
            return decision;
        }
        frame->phase = SceneFramePhase::world;
        return decision;
    }
    if (IsUiLayer(classification.layer)) {
        if (frame->phase == SceneFramePhase::awaiting_world) {
            return decision;
        }
        if (frame->phase == SceneFramePhase::world
            && !frame->composite_requested) {
            frame->composite_requested = true;
            ++frame->boundary_count;
            decision.composite_before_draw = true;
        }
        frame->phase = SceneFramePhase::ui;
    }
    return decision;
}

}  // namespace wonderbane::extension
