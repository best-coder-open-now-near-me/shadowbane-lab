#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

struct OutlineBounds {
    float minimum[3];
    float maximum[3];
};

struct OutlineHullTransform {
    float center[3];
    float scale[3];
    float half_extent[3];
};

bool IsPerspectiveProjectionMatrix(const float* matrix, std::size_t count) noexcept;
bool IsLocalOutlineModelViewMatrix(const float* matrix, std::size_t count) noexcept;
bool IsPlanarOverlayGeometry(
    const OutlineBounds* bounds,
    std::size_t vertex_count,
    std::size_t primitive_count
) noexcept;
bool IsPlanarOverlayDrawState(
    bool planar_candidate,
    bool texture_enabled,
    bool alpha_test_enabled,
    bool blend_enabled,
    bool lighting_enabled,
    bool fog_enabled
) noexcept;
bool IsFeatureAccentDrawState(
    bool local_model,
    bool depth_writes,
    bool blend_enabled,
    bool lighting_enabled
) noexcept;
float PerspectiveOutlineLineWidth(
    const float* projection,
    std::size_t projection_count,
    const float* model_view,
    std::size_t model_view_count,
    const int* viewport,
    std::size_t viewport_count
) noexcept;
float InteriorContourLineWidth(float outline_width) noexcept;
std::size_t TriangleFeatureEdgeCount(
    const float* vertices,
    std::size_t float_count
) noexcept;
bool ExpandOutlineBounds(OutlineBounds* bounds, float x, float y, float z) noexcept;
bool CenteredOutlineHullTransform(
    const OutlineBounds* bounds,
    float world_thickness,
    OutlineHullTransform* transform
) noexcept;
bool IsOutlinePrimitive(unsigned int mode, int count) noexcept;

DWORD StartStrongCelShading() noexcept;
void StopStrongCelShading() noexcept;
DWORD StartGraphicsPresentObservation() noexcept;
void StopGraphicsPresentObservation() noexcept;

}  // namespace wonderbane::extension
