#pragma once

#include <cstddef>
#include <cstdint>
#include <span>

namespace wonderbane::extension {

// Startup-only, full-renderer repair. No client object reads or GL calls.
// Unknown code stays stock. Stop restores only bytes still owned by this repair.
void StartTerrainMaskRefresh(std::uint8_t* image, std::size_t image_size,
    const char* verified_executable_sha256) noexcept;
void StopTerrainMaskRefresh() noexcept;
const char* TerrainMaskRefreshStatusJson() noexcept;
// Normalize only this process's fully installed, reviewed repair in a verifier's
// private code copy. Disk bytes must still be the authenticated original bytes.
// Never changes client code; stock/unowned code is left for strict comparison.
bool NormalizeOwnedTerrainMaskRefreshCode(std::uintptr_t image, std::uint32_t text_rva,
    std::span<std::uint8_t> code, std::span<const std::uint8_t> disk) noexcept;

}  // namespace wonderbane::extension
