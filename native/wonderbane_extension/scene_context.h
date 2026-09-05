#pragma once
#include <Windows.h>
#include <cstddef>
#include <cstdint>
namespace wonderbane::extension {
// One idempotent, process-pinned context boundary, independent of feature start.
// It remains installed for deferred owning-context cleanup; no hot-unload API.
DWORD StartSceneContextObservation(std::uint8_t* image, std::size_t size) noexcept;
}
