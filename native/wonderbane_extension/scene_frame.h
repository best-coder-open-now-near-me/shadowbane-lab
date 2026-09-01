#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

enum class DrawSubmission : std::uint8_t {
    immediate,
    display_list,
    arrays,
    elements,
};

enum class DrawProjection : std::uint8_t {
    unknown,
    perspective,
    orthographic,
};

enum class DrawLayer : std::uint8_t {
    unknown,
    world_opaque,
    world_alpha_tested,
    world_translucent,
    world_overlay,
    ui_overlay,
    count,
};

enum class DrawClassificationReason : std::uint8_t {
    projection_unavailable,
    orthographic_projection,
    planar_overlay_state,
    depth_writing_opaque,
    depth_writing_alpha_tested,
    blended_perspective,
    depthless_perspective,
    count,
};

struct FixedFunctionDrawState {
    DrawSubmission submission = DrawSubmission::immediate;
    DrawProjection projection = DrawProjection::unknown;
    bool planar_overlay_candidate = false;
    bool depth_writes = false;
    bool depth_test_enabled = false;
    bool texture_enabled = false;
    bool alpha_test_enabled = false;
    bool blend_enabled = false;
    bool lighting_enabled = false;
    bool fog_enabled = false;
};

struct DrawClassification {
    DrawLayer layer = DrawLayer::unknown;
    DrawClassificationReason reason =
        DrawClassificationReason::projection_unavailable;
};

enum class SceneFramePhase : std::uint8_t {
    awaiting_world,
    world,
    ui,
};

constexpr std::size_t kDrawLayerCount =
    static_cast<std::size_t>(DrawLayer::count);
constexpr std::size_t kDrawClassificationReasonCount =
    static_cast<std::size_t>(DrawClassificationReason::count);

struct SceneFrameState {
    SceneFramePhase phase = SceneFramePhase::awaiting_world;
    std::array<std::uint64_t, kDrawLayerCount> draw_counts{};
    std::array<std::uint64_t, kDrawClassificationReasonCount> reason_counts{};
    std::uint64_t draw_count = 0U;
    std::uint64_t world_draw_count = 0U;
    std::uint64_t boundary_count = 0U;
    std::uint64_t late_world_draw_count = 0U;
    std::uint64_t composite_candidate_count = 0U;
    std::uint64_t rejected_composite_candidate_count = 0U;
    std::uint64_t first_world_draw_ordinal = 0U;
    std::uint64_t first_composite_candidate_draw_ordinal = 0U;
    std::uint64_t accepted_boundary_draw_ordinal = 0U;
    std::uint64_t first_late_world_draw_ordinal = 0U;
    std::uint64_t last_world_draw_ordinal = 0U;
    std::uint64_t fixed_function_refresh_count = 0U;
    bool composite_requested = false;
};

struct SceneFrameDecision {
    DrawClassification classification{};
    bool contributes_to_scene = false;
    bool composite_before_draw = false;
};

DrawClassification ClassifyFixedFunctionDraw(
    const FixedFunctionDrawState& state
) noexcept;
bool IsWorldLayer(DrawLayer layer) noexcept;
bool IsUiLayer(DrawLayer layer) noexcept;
bool IsSceneCompositeCandidate(
    const DrawClassification& classification
) noexcept;
const char* DrawLayerName(DrawLayer layer) noexcept;
const char* DrawClassificationReasonName(
    DrawClassificationReason reason
) noexcept;
SceneFrameDecision AdvanceSceneFrame(
    SceneFrameState* frame,
    const DrawClassification& classification
) noexcept;
void ResolveSceneCompositeAttempt(
    SceneFrameState* frame,
    bool accepted
) noexcept;

}  // namespace wonderbane::extension
