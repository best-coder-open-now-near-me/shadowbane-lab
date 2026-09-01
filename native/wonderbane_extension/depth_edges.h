#pragma once

#include <cstddef>

namespace wonderbane::extension {

float ReconstructPerspectiveEyeDepth(
    float window_depth,
    float projection_10,
    float projection_11,
    float projection_14
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

void MarkDepthEdgeSceneDraw(
    const float* projection,
    std::size_t projection_count,
    const int* viewport,
    std::size_t viewport_count
) noexcept;
void CompositeDepthEdgesBeforeUi() noexcept;
void EndDepthEdgeFrame() noexcept;
void ResetDepthEdges() noexcept;

}  // namespace wonderbane::extension
