#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

enum class CelShadingProfile : std::uint32_t {
    native = 0U,
    flat = 1U,
    outlined = 2U,
};

struct OutlineBounds {
    float minimum[3];
    float maximum[3];
};

struct OutlineHullTransform {
    float center[3];
    float scale;
};

std::uint32_t* FindImportAddressSlot(
    std::uint8_t* image,
    std::size_t image_size,
    const char* library_name,
    const char* symbol_name
) noexcept;

bool IsPerspectiveProjectionMatrix(const float* matrix, std::size_t count) noexcept;
bool IsLocalOutlineModelViewMatrix(const float* matrix, std::size_t count) noexcept;
float PerspectiveOutlineLineWidth(
    const float* projection,
    std::size_t projection_count,
    const float* model_view,
    std::size_t model_view_count,
    const int* viewport,
    std::size_t viewport_count
) noexcept;
bool ExpandOutlineBounds(OutlineBounds* bounds, float x, float y, float z) noexcept;
bool CenteredOutlineHullTransform(
    const OutlineBounds* bounds,
    float world_thickness,
    OutlineHullTransform* transform
) noexcept;
bool IsOutlinePrimitive(unsigned int mode, int count) noexcept;
std::size_t CelShadingHookCount(CelShadingProfile profile) noexcept;
DWORD SelectCelShadingProfile(
    const wchar_t* configured_value,
    CelShadingProfile* profile
) noexcept;

DWORD StartStrongCelShading(CelShadingProfile profile) noexcept;
void StopStrongCelShading() noexcept;

}  // namespace wonderbane::extension
