#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

bool HasGraphicsExtensionToken(
    const char* extensions,
    const char* token
) noexcept;
bool IsGraphicsVersionAtLeast(
    const char* version,
    unsigned int required_major,
    unsigned int required_minor
) noexcept;

DWORD StartGraphicsStatusPublication() noexcept;
DWORD ConfigureGraphicsPresentEntry(
    const char* library_name,
    const char* symbol_name,
    std::uint32_t iat_rva,
    const char* runtime_profile
) noexcept;
void ObserveGraphicsPresent() noexcept;
void StopGraphicsStatusPublication() noexcept;
DWORD GetGraphicsStatusPath(
    wchar_t* destination,
    std::size_t destination_capacity
) noexcept;

}  // namespace wonderbane::extension
