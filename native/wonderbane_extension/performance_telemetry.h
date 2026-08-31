#pragma once

#include "event_channel.h"

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

constexpr char kPerformanceTelemetryMagic[8] = {'W', 'B', 'P', 'E', 'R', 'F', '1', '\0'};
constexpr std::uint32_t kPerformanceTelemetrySchemaVersion = 1U;
constexpr std::uint32_t kPerformanceTelemetryHeaderSize = 128U;
constexpr std::uint32_t kPerformanceTelemetrySlotSize = 96U;
constexpr std::uint32_t kPerformanceTelemetryCapacity = 8192U;
constexpr std::uint32_t kPerformanceFrameGapKind = 1U;
constexpr std::uint32_t kPerformanceCacheReadKind = 2U;
constexpr std::uint32_t kPerformanceTextureImageKind = 3U;
constexpr std::uint32_t kPerformanceTextureSubImageKind = 4U;
constexpr std::uint32_t kPerformanceSuccessFlag = 1U << 0U;
constexpr std::uint32_t kPerformanceWin32IoFlag = 1U << 1U;
constexpr std::uint32_t kPerformanceStdioIoFlag = 1U << 2U;
constexpr std::uint32_t kPerformancePixelsPresentFlag = 1U << 3U;
constexpr std::uint32_t kPerformanceHookCount = 21U;
constexpr std::size_t kPerformanceTelemetrySize =
    kPerformanceTelemetryHeaderSize
    + kPerformanceTelemetrySlotSize * kPerformanceTelemetryCapacity;

enum class CacheArchiveKind : std::uint32_t {
    none = 0U,
    textures = 1U,
    mesh = 2U,
    render = 3U,
    objects = 4U,
    zones = 5U,
    terrain_alpha = 6U,
    tile = 7U,
    other = 255U,
};

#pragma pack(push, 1)
struct PerformanceTelemetryHeader {
    char magic[8];
    std::uint32_t schema_version;
    std::uint32_t header_size;
    std::uint32_t slot_size;
    std::uint32_t capacity;
    std::uint32_t process_id;
    std::uint32_t capability_flags;
    std::uint64_t process_creation_filetime_utc;
    std::uint64_t qpc_frequency;
    std::uint64_t started_qpc;
    volatile LONG64 write_sequence;
    volatile LONG64 overwritten_record_count;
    volatile LONG64 frame_count;
    volatile LONG64 slow_frame_count;
    volatile LONG64 cache_read_count;
    volatile LONG64 cache_read_bytes;
    volatile LONG64 texture_upload_count;
    volatile LONG64 texture_upload_bytes;
    volatile LONG producer_error;
    volatile LONG active_hook_count;
};

struct PerformanceTelemetrySlot {
    volatile LONG64 committed_sequence;
    std::uint32_t kind;
    std::uint32_t flags;
    std::uint64_t started_qpc;
    std::uint64_t duration_qpc;
    std::uint32_t thread_id;
    std::uint32_t archive_kind;
    std::uint64_t byte_count;
    std::uint64_t argument0;
    std::uint64_t argument1;
    std::uint64_t argument2;
    std::uint64_t frame_interval_qpc;
    std::uint64_t pipeline_gap_qpc;
    std::uint64_t reserved;
};

struct PerformanceTelemetryStorage {
    PerformanceTelemetryHeader header;
    PerformanceTelemetrySlot slots[kPerformanceTelemetryCapacity];
};
#pragma pack(pop)

static_assert(sizeof(PerformanceTelemetryHeader) == kPerformanceTelemetryHeaderSize);
static_assert(sizeof(PerformanceTelemetrySlot) == kPerformanceTelemetrySlotSize);
static_assert(sizeof(PerformanceTelemetryStorage) == kPerformanceTelemetrySize);
static_assert(offsetof(PerformanceTelemetryHeader, write_sequence) % alignof(LONG64) == 0U);
static_assert(offsetof(PerformanceTelemetrySlot, committed_sequence) == 0U);

DWORD FormatPerformanceTelemetryMappingName(
    const ProcessIdentity& identity,
    wchar_t* destination,
    std::size_t destination_capacity
) noexcept;
CacheArchiveKind ClassifyCacheArchivePath(const char* file_name) noexcept;
CacheArchiveKind ClassifyCacheArchivePath(const wchar_t* file_name) noexcept;
std::uint64_t EstimateTextureUploadBytes(
    int width,
    int height,
    unsigned int format,
    unsigned int type
) noexcept;
DWORD StartPerformanceTelemetry(const ProcessIdentity& identity) noexcept;
void StopPerformanceTelemetry() noexcept;

}  // namespace wonderbane::extension
