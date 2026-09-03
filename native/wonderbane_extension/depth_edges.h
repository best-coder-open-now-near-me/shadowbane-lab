#pragma once

#include <cstddef>

namespace wonderbane::extension {

struct DepthContourEvaluation {
    float horizontal_response = 0.0F;
    float vertical_response = 0.0F;
    float horizontal_support = 0.0F;
    float vertical_support = 0.0F;
    bool raw_candidate = false;
    bool accepted = false;
};

float ReconstructPerspectiveEyeDepth(
    float window_depth,
    float projection_10,
    float projection_11,
    float projection_14
) noexcept;
DepthContourEvaluation EvaluateDepthContour(
    float center_depth,
    const float* neighbour_depths,
    std::size_t neighbour_count,
    float projection_10,
    float projection_11,
    float projection_14,
    float edge_threshold,
    float sustained_edge_threshold,
    bool require_sustained_support
) noexcept;
bool IsForegroundDepthDiscontinuity(
    float center_depth,
    const float* neighbour_depths,
    std::size_t neighbour_count,
    float projection_10,
    float projection_11,
    float projection_14
) noexcept;
const char* DepthEdgeFragmentSource() noexcept;
const char* DepthEdgeVertexSource() noexcept;

bool BeginMainDepthEdgeScene(
    const float* projection,
    std::size_t projection_count,
    const int* viewport,
    std::size_t viewport_count
) noexcept;
void MarkDepthEdgeSceneDraw() noexcept;
bool CompositeDepthEdgesBeforeUi() noexcept;
void DiscardPendingDepthEdgeScene() noexcept;
void EndDepthEdgeFrame() noexcept;
void ResetDepthEdges() noexcept;

}  // namespace wonderbane::extension
