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

DWORD StartStrongCelShading() noexcept;
void StopStrongCelShading() noexcept;

}  // namespace wonderbane::extension
