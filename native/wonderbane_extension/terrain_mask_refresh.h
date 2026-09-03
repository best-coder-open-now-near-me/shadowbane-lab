#pragma once

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

// Startup-only, full-renderer repair. No client object reads or GL calls.
// Unknown code stays stock. Stop restores only bytes still owned by this repair.
void StartTerrainMaskRefresh(std::uint8_t* image, std::size_t image_size,
    const char* verified_executable_sha256) noexcept;
void StopTerrainMaskRefresh() noexcept;
const char* TerrainMaskRefreshStatusJson() noexcept;

}  // namespace wonderbane::extension
