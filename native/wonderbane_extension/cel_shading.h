#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

enum class CelShadingProfile : std::uint32_t {
    flat = 0U,
    outlined = 1U,
};

bool IsPerspectiveProjectionMatrix(const float* matrix, std::size_t count) noexcept;
bool IsOutlinePrimitive(unsigned int mode, int count) noexcept;
DWORD SelectCelShadingProfile(
    const wchar_t* configured_value,
    CelShadingProfile* profile
) noexcept;

DWORD StartStrongCelShading(CelShadingProfile profile) noexcept;
void StopStrongCelShading() noexcept;

}  // namespace wonderbane::extension
