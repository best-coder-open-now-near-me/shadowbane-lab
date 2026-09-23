#pragma once

#include <Windows.h>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

// An opt-in observer, not a terrain classifier or a new trusted client mapping.
// All entry points are no-ops until StartTerrainTrace accepts the launch opt-in.
enum class TerrainSubmission : unsigned int { immediate, list, lists, arrays, elements, multi_elements };
void StartTerrainTrace(const wchar_t* graphics_status_path, std::uintptr_t image_base,
    std::size_t image_size, const char* executable_sha256) noexcept;
void StopTerrainTrace() noexcept;
void TerrainTraceClear(bool reviewed_main_clear, unsigned int mask) noexcept;
void TerrainTraceDone3d() noexcept;
// Read-only phase query; no GL calls and false unless an opt-in frame is active.
bool IsTerrainTraceCapturing() noexcept;
// multi_elements records count as subdraws, not summed indices or fragments.
void TerrainTraceDraw(TerrainSubmission submission, std::uintptr_t caller,
    unsigned int mode, int first, int count, unsigned int index_type,
    unsigned int list, bool list_source_stable, bool query_safe) noexcept;
// True means immutable evidence is ready for the graphics publisher thread.
bool TerrainTracePresent() noexcept;
void PublishPendingTerrainTrace() noexcept;

}  // namespace wonderbane::extension
