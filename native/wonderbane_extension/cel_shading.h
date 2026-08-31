#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

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
bool IsOutlinePrimitive(unsigned int mode, int count) noexcept;

DWORD StartStrongCelShading() noexcept;
void StopStrongCelShading() noexcept;

}  // namespace wonderbane::extension
