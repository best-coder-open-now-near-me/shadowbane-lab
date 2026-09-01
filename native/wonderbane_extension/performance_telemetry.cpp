#include "performance_telemetry.h"

#include "import_hook.h"

#include <strsafe.h>

#include <array>
#include <cerrno>
#include <cstdio>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace wonderbane::extension {
namespace {

constexpr std::size_t kTrackedStreamCapacity = 64U;
constexpr std::uint64_t kUnknownOffset = std::numeric_limits<std::uint64_t>::max();
constexpr std::uint64_t kSlowFrameMicroseconds = 40'000U;
constexpr std::uint64_t kMaximumPipelineGapSeconds = 5U;

using CreateFileAFunction = HANDLE(WINAPI*)(
    LPCSTR file_name,
    DWORD desired_access,
    DWORD share_mode,
    LPSECURITY_ATTRIBUTES security_attributes,
    DWORD creation_disposition,
    DWORD flags_and_attributes,
    HANDLE template_file
);
using ReadFileFunction = BOOL(WINAPI*)(
    HANDLE file,
    LPVOID buffer,
    DWORD requested_bytes,
    LPDWORD completed_bytes,
    LPOVERLAPPED overlapped
);
using SetFilePointerFunction = DWORD(WINAPI*)(
    HANDLE file,
    LONG distance_low,
    PLONG distance_high,
    DWORD move_method
);
using CloseHandleFunction = BOOL(WINAPI*)(HANDLE object);
using FopenFunction = std::FILE*(__cdecl*)(const char* file_name, const char* mode);
using WfopenFunction = std::FILE*(__cdecl*)(const wchar_t* file_name, const wchar_t* mode);
using FreadFunction = std::size_t(__cdecl*)(
    void* buffer,
    std::size_t element_size,
    std::size_t element_count,
    std::FILE* stream
);
using FseekFunction = int(__cdecl*)(std::FILE* stream, long offset, int origin);
using FcloseFunction = int(__cdecl*)(std::FILE* stream);
using GlTexImage2DFunction = void(APIENTRY*)(
    unsigned int target,
    int level,
    int internal_format,
    int width,
    int height,
    int border,
    unsigned int format,
    unsigned int type,
    const void* pixels
);
using GlTexSubImage2DFunction = void(APIENTRY*)(
    unsigned int target,
    int level,
    int x_offset,
    int y_offset,
    int width,
    int height,
    unsigned int format,
    unsigned int type,
    const void* pixels
);

struct TrackedHandle {
    HANDLE handle;
    CacheArchiveKind archive;
    std::uint64_t offset;
};

struct TrackedFile {
    std::FILE* stream;
    CacheArchiveKind archive;
    std::uint64_t offset;
};

struct LoaderContext {
    std::uint64_t completed_qpc;
    CacheArchiveKind archive;
};

struct FrameTotals {
    std::uint64_t cache_read_count;
    std::uint64_t cache_read_bytes;
    std::uint64_t cache_read_duration_qpc;
    std::uint64_t texture_upload_count;
    std::uint64_t texture_upload_bytes;
    std::uint64_t texture_upload_duration_qpc;
};

struct HookPlan {
    const wchar_t* image_module_name;
    const char* import_library_name;
    const wchar_t* api_module_name;
    const char* symbol_name;
    PVOID replacement;
    PVOID original;
    std::uint32_t* slot;
    PVOID volatile* original_storage;
    std::uint32_t** slot_storage;
    std::uint32_t capability;
};

HANDLE g_mapping = nullptr;
PerformanceTelemetryStorage* g_storage = nullptr;
SRWLOCK g_publish_lock = SRWLOCK_INIT;
SRWLOCK g_stream_lock = SRWLOCK_INIT;
SRWLOCK g_aggregate_lock = SRWLOCK_INIT;
std::array<TrackedHandle, kTrackedStreamCapacity> g_handles{};
std::array<TrackedFile, kTrackedStreamCapacity> g_files{};
std::uint64_t g_previous_present_qpc = 0U;
FrameTotals g_frame_totals{};
FrameTotals g_pending_frame_totals{};
volatile LONG g_profile = static_cast<LONG>(PerformanceTelemetryProfile::disabled);
thread_local LoaderContext g_loader_context{};

PVOID volatile g_original_create_file_a = nullptr;
PVOID volatile g_original_read_file = nullptr;
PVOID volatile g_original_set_file_pointer = nullptr;
PVOID volatile g_original_close_handle = nullptr;
PVOID volatile g_original_fopen = nullptr;
PVOID volatile g_original_wfopen = nullptr;
PVOID volatile g_original_fread = nullptr;
PVOID volatile g_original_fseek = nullptr;
PVOID volatile g_original_fclose = nullptr;
PVOID volatile g_original_tex_image_2d = nullptr;
PVOID volatile g_original_tex_sub_image_2d = nullptr;

std::array<std::uint32_t*, kPerformanceHookCount + 1U> g_hook_slots{};

template <typename Function>
Function LoadFunction(PVOID volatile* const storage) noexcept {
    return reinterpret_cast<Function>(InterlockedCompareExchangePointer(
        storage,
        nullptr,
        nullptr
    ));
}

std::uint64_t QueryCounter() noexcept {
    LARGE_INTEGER value{};
    return QueryPerformanceCounter(&value) != FALSE
        ? static_cast<std::uint64_t>(value.QuadPart)
        : 0U;
}

bool EqualAsciiInsensitive(const char* left, const char* right) noexcept {
    if (left == nullptr || right == nullptr) {
        return false;
    }
    while (*left != '\0' && *right != '\0') {
        const auto fold = [](const unsigned char value) noexcept {
            return value >= static_cast<unsigned char>('A')
                    && value <= static_cast<unsigned char>('Z')
                ? static_cast<unsigned char>(value + ('a' - 'A'))
                : value;
        };
        if (fold(static_cast<unsigned char>(*left)) != fold(static_cast<unsigned char>(*right))) {
            return false;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

bool EqualAsciiInsensitive(const wchar_t* left, const wchar_t* right) noexcept {
    if (left == nullptr || right == nullptr) {
        return false;
    }
    while (*left != L'\0' && *right != L'\0') {
        const auto fold = [](const wchar_t value) noexcept {
            return value >= L'A' && value <= L'Z' ? value + (L'a' - L'A') : value;
        };
        if (fold(*left) != fold(*right)) {
            return false;
        }
        ++left;
        ++right;
    }
    return *left == L'\0' && *right == L'\0';
}

template <typename Character>
const Character* BaseName(const Character* path) noexcept {
    if (path == nullptr) {
        return nullptr;
    }
    const Character* name = path;
    for (const Character* cursor = path; *cursor != 0; ++cursor) {
        if (*cursor == static_cast<Character>('\\') || *cursor == static_cast<Character>('/')) {
            name = cursor + 1;
        }
    }
    return name;
}

template <typename Character>
CacheArchiveKind ClassifyCacheName(const Character* file_name) noexcept {
    const Character* const name = BaseName(file_name);
    if (name == nullptr) {
        return CacheArchiveKind::none;
    }
    struct KnownArchive {
        const char* narrow;
        const wchar_t* wide;
        CacheArchiveKind kind;
    };
    constexpr std::array<KnownArchive, 7U> known{{
        {"Textures.cache", L"Textures.cache", CacheArchiveKind::textures},
        {"Mesh.cache", L"Mesh.cache", CacheArchiveKind::mesh},
        {"Render.cache", L"Render.cache", CacheArchiveKind::render},
        {"CObjects.cache", L"CObjects.cache", CacheArchiveKind::objects},
        {"CZone.cache", L"CZone.cache", CacheArchiveKind::zones},
        {"TerrainAlpha.cache", L"TerrainAlpha.cache", CacheArchiveKind::terrain_alpha},
        {"Tile.cache", L"Tile.cache", CacheArchiveKind::tile},
    }};
    for (const KnownArchive& archive : known) {
        if constexpr (sizeof(Character) == sizeof(char)) {
            if (EqualAsciiInsensitive(reinterpret_cast<const char*>(name), archive.narrow)) {
                return archive.kind;
            }
        } else {
            if (EqualAsciiInsensitive(reinterpret_cast<const wchar_t*>(name), archive.wide)) {
                return archive.kind;
            }
        }
    }
    const Character cache_suffix[] = {
        static_cast<Character>('.'),
        static_cast<Character>('c'),
        static_cast<Character>('a'),
        static_cast<Character>('c'),
        static_cast<Character>('h'),
        static_cast<Character>('e'),
        0,
    };
    std::size_t length = 0U;
    while (name[length] != 0) {
        ++length;
    }
    constexpr std::size_t suffix_length = 6U;
    if (length < suffix_length) {
        return CacheArchiveKind::none;
    }
    const Character* const suffix = name + length - suffix_length;
    if constexpr (sizeof(Character) == sizeof(char)) {
        return EqualAsciiInsensitive(
                   reinterpret_cast<const char*>(suffix),
                   reinterpret_cast<const char*>(cache_suffix)
               )
            ? CacheArchiveKind::other
            : CacheArchiveKind::none;
    } else {
        return EqualAsciiInsensitive(
                   reinterpret_cast<const wchar_t*>(suffix),
                   reinterpret_cast<const wchar_t*>(cache_suffix)
               )
            ? CacheArchiveKind::other
            : CacheArchiveKind::none;
    }
}

template <typename Entry, typename Key>
Entry* FindTracked(std::array<Entry, kTrackedStreamCapacity>& entries, const Key key) noexcept {
    for (Entry& entry : entries) {
        if (entry.handle == key) {
            return &entry;
        }
    }
    return nullptr;
}

template <>
TrackedFile* FindTracked(
    std::array<TrackedFile, kTrackedStreamCapacity>& entries,
    std::FILE* const key
) noexcept {
    for (TrackedFile& entry : entries) {
        if (entry.stream == key) {
            return &entry;
        }
    }
    return nullptr;
}

void TrackHandle(const HANDLE handle, const CacheArchiveKind archive) noexcept {
    if (handle == nullptr || handle == INVALID_HANDLE_VALUE || archive == CacheArchiveKind::none) {
        return;
    }
    AcquireSRWLockExclusive(&g_stream_lock);
    for (TrackedHandle& entry : g_handles) {
        if (entry.handle == nullptr) {
            entry = {handle, archive, 0U};
            break;
        }
    }
    ReleaseSRWLockExclusive(&g_stream_lock);
}

void TrackFile(std::FILE* const stream, const CacheArchiveKind archive) noexcept {
    if (stream == nullptr || archive == CacheArchiveKind::none) {
        return;
    }
    AcquireSRWLockExclusive(&g_stream_lock);
    for (TrackedFile& entry : g_files) {
        if (entry.stream == nullptr) {
            entry = {stream, archive, 0U};
            break;
        }
    }
    ReleaseSRWLockExclusive(&g_stream_lock);
}

bool SnapshotHandle(
    const HANDLE handle,
    CacheArchiveKind* const archive,
    std::uint64_t* const offset
) noexcept {
    bool found = false;
    AcquireSRWLockShared(&g_stream_lock);
    TrackedHandle* const entry = FindTracked(g_handles, handle);
    if (entry != nullptr) {
        *archive = entry->archive;
        *offset = entry->offset;
        found = true;
    }
    ReleaseSRWLockShared(&g_stream_lock);
    return found;
}

bool SnapshotFile(
    std::FILE* const stream,
    CacheArchiveKind* const archive,
    std::uint64_t* const offset
) noexcept {
    bool found = false;
    AcquireSRWLockShared(&g_stream_lock);
    TrackedFile* const entry = FindTracked(g_files, stream);
    if (entry != nullptr) {
        *archive = entry->archive;
        *offset = entry->offset;
        found = true;
    }
    ReleaseSRWLockShared(&g_stream_lock);
    return found;
}

void AdvanceHandle(const HANDLE handle, const std::uint64_t completed) noexcept {
    AcquireSRWLockExclusive(&g_stream_lock);
    TrackedHandle* const entry = FindTracked(g_handles, handle);
    if (entry != nullptr && entry->offset != kUnknownOffset) {
        entry->offset = completed <= kUnknownOffset - entry->offset
            ? entry->offset + completed
            : kUnknownOffset;
    }
    ReleaseSRWLockExclusive(&g_stream_lock);
}

void AdvanceFile(std::FILE* const stream, const std::uint64_t completed) noexcept {
    AcquireSRWLockExclusive(&g_stream_lock);
    TrackedFile* const entry = FindTracked(g_files, stream);
    if (entry != nullptr && entry->offset != kUnknownOffset) {
        entry->offset = completed <= kUnknownOffset - entry->offset
            ? entry->offset + completed
            : kUnknownOffset;
    }
    ReleaseSRWLockExclusive(&g_stream_lock);
}

template <typename Entry, typename Key>
void RemoveTracked(std::array<Entry, kTrackedStreamCapacity>& entries, const Key key) noexcept {
    AcquireSRWLockExclusive(&g_stream_lock);
    Entry* const entry = FindTracked(entries, key);
    if (entry != nullptr) {
        *entry = {};
    }
    ReleaseSRWLockExclusive(&g_stream_lock);
}

std::uint64_t SaturatingProduct(
    const std::uint64_t left,
    const std::uint64_t right
) noexcept {
    return left == 0U || right <= std::numeric_limits<std::uint64_t>::max() / left
        ? left * right
        : std::numeric_limits<std::uint64_t>::max();
}

std::uint64_t SaturatingAdd(
    const std::uint64_t left,
    const std::uint64_t right
) noexcept {
    return right <= std::numeric_limits<std::uint64_t>::max() - left
        ? left + right
        : std::numeric_limits<std::uint64_t>::max();
}

bool AggregateProfileSelected() noexcept {
    return InterlockedCompareExchange(&g_profile, 0, 0)
        == static_cast<LONG>(PerformanceTelemetryProfile::aggregate);
}

void AddAggregateCacheRead(
    const std::uint64_t bytes,
    const std::uint64_t duration_qpc
) noexcept {
    AcquireSRWLockExclusive(&g_aggregate_lock);
    g_frame_totals.cache_read_count = SaturatingAdd(g_frame_totals.cache_read_count, 1U);
    g_frame_totals.cache_read_bytes = SaturatingAdd(g_frame_totals.cache_read_bytes, bytes);
    g_frame_totals.cache_read_duration_qpc = SaturatingAdd(
        g_frame_totals.cache_read_duration_qpc,
        duration_qpc
    );
    ReleaseSRWLockExclusive(&g_aggregate_lock);
}

void AddAggregateTextureUpload(
    const std::uint64_t bytes,
    const std::uint64_t duration_qpc
) noexcept {
    AcquireSRWLockExclusive(&g_aggregate_lock);
    g_frame_totals.texture_upload_count = SaturatingAdd(
        g_frame_totals.texture_upload_count,
        1U
    );
    g_frame_totals.texture_upload_bytes = SaturatingAdd(g_frame_totals.texture_upload_bytes, bytes);
    g_frame_totals.texture_upload_duration_qpc = SaturatingAdd(
        g_frame_totals.texture_upload_duration_qpc,
        duration_qpc
    );
    ReleaseSRWLockExclusive(&g_aggregate_lock);
}

std::uint64_t EstimateTextureBytes(
    const int width,
    const int height,
    const unsigned int format,
    const unsigned int type
) noexcept {
    if (width <= 0 || height <= 0) {
        return 0U;
    }
    std::uint64_t components = 4U;
    switch (format) {
        case 0x1906U:  // GL_ALPHA
        case 0x1909U:  // GL_LUMINANCE
            components = 1U;
            break;
        case 0x190AU:  // GL_LUMINANCE_ALPHA
            components = 2U;
            break;
        case 0x1907U:  // GL_RGB
        case 0x80E0U:  // GL_BGR
            components = 3U;
            break;
        default:
            break;
    }
    std::uint64_t component_bytes = 1U;
    switch (type) {
        case 0x1402U:  // GL_SHORT
        case 0x1403U:  // GL_UNSIGNED_SHORT
            component_bytes = 2U;
            break;
        case 0x1404U:  // GL_INT
        case 0x1405U:  // GL_UNSIGNED_INT
        case 0x1406U:  // GL_FLOAT
            component_bytes = 4U;
            break;
        case 0x8032U:  // GL_UNSIGNED_BYTE_3_3_2
        case 0x8362U:  // GL_UNSIGNED_BYTE_2_3_3_REV
            components = 1U;
            component_bytes = 1U;
            break;
        case 0x8033U:  // GL_UNSIGNED_SHORT_4_4_4_4
        case 0x8034U:  // GL_UNSIGNED_SHORT_5_5_5_1
        case 0x8363U:  // GL_UNSIGNED_SHORT_5_6_5
            components = 1U;
            component_bytes = 2U;
            break;
        case 0x8035U:  // GL_UNSIGNED_INT_8_8_8_8
        case 0x8036U:  // GL_UNSIGNED_INT_10_10_10_2
            components = 1U;
            component_bytes = 4U;
            break;
        default:
            break;
    }
    return SaturatingProduct(
        SaturatingProduct(static_cast<std::uint64_t>(width), static_cast<std::uint64_t>(height)),
        SaturatingProduct(components, component_bytes)
    );
}

void Publish(
    const std::uint32_t kind,
    const std::uint32_t flags,
    const std::uint64_t started_qpc,
    const std::uint64_t duration_qpc,
    const CacheArchiveKind archive,
    const std::uint64_t byte_count,
    const std::uint64_t argument0,
    const std::uint64_t argument1,
    const std::uint64_t argument2,
    const std::uint64_t frame_interval_qpc,
    const std::uint64_t pipeline_gap_qpc,
    const std::uint64_t reserved = 0U
) noexcept {
    if (g_storage == nullptr) {
        return;
    }
    AcquireSRWLockExclusive(&g_publish_lock);
    const LONG64 previous = InterlockedCompareExchange64(
        &g_storage->header.write_sequence,
        0,
        0
    );
    if (previous < 0 || previous == std::numeric_limits<LONG64>::max()) {
        InterlockedExchange(&g_storage->header.producer_error, ERROR_ARITHMETIC_OVERFLOW);
        ReleaseSRWLockExclusive(&g_publish_lock);
        return;
    }
    const LONG64 sequence = previous + 1;
    const std::size_t slot_index = static_cast<std::size_t>(
        previous % static_cast<LONG64>(kPerformanceTelemetryCapacity)
    );
    PerformanceTelemetrySlot& slot = g_storage->slots[slot_index];
    InterlockedExchange64(&slot.committed_sequence, 0);
    slot.kind = kind;
    slot.flags = flags;
    slot.started_qpc = started_qpc;
    slot.duration_qpc = duration_qpc;
    slot.thread_id = GetCurrentThreadId();
    slot.archive_kind = static_cast<std::uint32_t>(archive);
    slot.byte_count = byte_count;
    slot.argument0 = argument0;
    slot.argument1 = argument1;
    slot.argument2 = argument2;
    slot.frame_interval_qpc = frame_interval_qpc;
    slot.pipeline_gap_qpc = pipeline_gap_qpc;
    slot.reserved = reserved;
    MemoryBarrier();
    InterlockedExchange64(&slot.committed_sequence, sequence);
    InterlockedExchange64(&g_storage->header.write_sequence, sequence);
    InterlockedExchange64(
        &g_storage->header.overwritten_record_count,
        sequence > static_cast<LONG64>(kPerformanceTelemetryCapacity)
            ? sequence - static_cast<LONG64>(kPerformanceTelemetryCapacity)
            : 0
    );
    InterlockedExchange(&g_storage->header.producer_error, ERROR_SUCCESS);
    ReleaseSRWLockExclusive(&g_publish_lock);
}

HANDLE WINAPI TelemetryCreateFileA(
    const LPCSTR file_name,
    const DWORD desired_access,
    const DWORD share_mode,
    const LPSECURITY_ATTRIBUTES security_attributes,
    const DWORD creation_disposition,
    const DWORD flags_and_attributes,
    const HANDLE template_file
) noexcept {
    const auto original = LoadFunction<CreateFileAFunction>(&g_original_create_file_a);
    if (original == nullptr) {
        SetLastError(ERROR_INVALID_FUNCTION);
        return INVALID_HANDLE_VALUE;
    }
    const HANDLE result = original(
        file_name,
        desired_access,
        share_mode,
        security_attributes,
        creation_disposition,
        flags_and_attributes,
        template_file
    );
    const DWORD last_error = GetLastError();
    if (result != INVALID_HANDLE_VALUE) {
        TrackHandle(result, ClassifyCacheArchivePath(file_name));
    }
    SetLastError(last_error);
    return result;
}

BOOL WINAPI TelemetryReadFile(
    const HANDLE file,
    const LPVOID buffer,
    const DWORD requested_bytes,
    const LPDWORD completed_bytes,
    const LPOVERLAPPED overlapped
) noexcept {
    const auto original = LoadFunction<ReadFileFunction>(&g_original_read_file);
    if (original == nullptr) {
        SetLastError(ERROR_INVALID_FUNCTION);
        return FALSE;
    }
    CacheArchiveKind archive = CacheArchiveKind::none;
    std::uint64_t offset = kUnknownOffset;
    const bool tracked = SnapshotHandle(file, &archive, &offset);
    if (tracked && overlapped != nullptr) {
        offset = static_cast<std::uint64_t>(overlapped->Offset)
            | static_cast<std::uint64_t>(overlapped->OffsetHigh) << 32U;
    }
    const std::uint64_t started = tracked ? QueryCounter() : 0U;
    const BOOL result = original(file, buffer, requested_bytes, completed_bytes, overlapped);
    const DWORD last_error = GetLastError();
    if (tracked) {
        const std::uint64_t completed = QueryCounter();
        const DWORD bytes = result != FALSE && completed_bytes != nullptr
            ? *completed_bytes
            : 0U;
        if (overlapped == nullptr) {
            AdvanceHandle(file, bytes);
        }
        InterlockedIncrement64(&g_storage->header.cache_read_count);
        InterlockedAdd64(&g_storage->header.cache_read_bytes, bytes);
        const std::uint64_t duration = completed >= started ? completed - started : 0U;
        if (AggregateProfileSelected()) {
            AddAggregateCacheRead(bytes, duration);
        } else {
            Publish(
                kPerformanceCacheReadKind,
                kPerformanceWin32IoFlag | (result != FALSE ? kPerformanceSuccessFlag : 0U),
                started,
                duration,
                archive,
                bytes,
                offset,
                requested_bytes,
                result != FALSE ? ERROR_SUCCESS : last_error,
                0U,
                0U
            );
        }
        g_loader_context = {completed, archive};
    }
    SetLastError(last_error);
    return result;
}

DWORD WINAPI TelemetrySetFilePointer(
    const HANDLE file,
    const LONG distance_low,
    const PLONG distance_high,
    const DWORD move_method
) noexcept {
    const auto original = LoadFunction<SetFilePointerFunction>(&g_original_set_file_pointer);
    if (original == nullptr) {
        SetLastError(ERROR_INVALID_FUNCTION);
        return INVALID_SET_FILE_POINTER;
    }
    const DWORD result = original(file, distance_low, distance_high, move_method);
    const DWORD last_error = GetLastError();
    CacheArchiveKind archive = CacheArchiveKind::none;
    std::uint64_t previous = kUnknownOffset;
    if (SnapshotHandle(file, &archive, &previous)) {
        std::uint64_t next = kUnknownOffset;
        if (distance_high != nullptr && !(result == INVALID_SET_FILE_POINTER && last_error != NO_ERROR)) {
            next = static_cast<std::uint64_t>(result)
                | static_cast<std::uint64_t>(static_cast<std::uint32_t>(*distance_high)) << 32U;
        } else if (result != INVALID_SET_FILE_POINTER || last_error == NO_ERROR) {
            if (move_method == FILE_BEGIN) {
                next = result;
            } else if (move_method == FILE_CURRENT && previous != kUnknownOffset) {
                const std::int64_t candidate = static_cast<std::int64_t>(previous)
                    + static_cast<std::int64_t>(distance_low);
                next = candidate >= 0 ? static_cast<std::uint64_t>(candidate) : kUnknownOffset;
            }
        }
        AcquireSRWLockExclusive(&g_stream_lock);
        TrackedHandle* const entry = FindTracked(g_handles, file);
        if (entry != nullptr) {
            entry->offset = next;
        }
        ReleaseSRWLockExclusive(&g_stream_lock);
    }
    SetLastError(last_error);
    return result;
}

BOOL WINAPI TelemetryCloseHandle(const HANDLE object) noexcept {
    const auto original = LoadFunction<CloseHandleFunction>(&g_original_close_handle);
    if (original == nullptr) {
        SetLastError(ERROR_INVALID_FUNCTION);
        return FALSE;
    }
    RemoveTracked(g_handles, object);
    return original(object);
}

std::FILE* __cdecl TelemetryFopen(const char* const file_name, const char* const mode) noexcept {
    const auto original = LoadFunction<FopenFunction>(&g_original_fopen);
    if (original == nullptr) {
        errno = EINVAL;
        return nullptr;
    }
    std::FILE* const result = original(file_name, mode);
    const int saved_errno = errno;
    TrackFile(result, ClassifyCacheArchivePath(file_name));
    errno = saved_errno;
    return result;
}

std::FILE* __cdecl TelemetryWfopen(
    const wchar_t* const file_name,
    const wchar_t* const mode
) noexcept {
    const auto original = LoadFunction<WfopenFunction>(&g_original_wfopen);
    if (original == nullptr) {
        errno = EINVAL;
        return nullptr;
    }
    std::FILE* const result = original(file_name, mode);
    const int saved_errno = errno;
    TrackFile(result, ClassifyCacheArchivePath(file_name));
    errno = saved_errno;
    return result;
}

std::size_t __cdecl TelemetryFread(
    void* const buffer,
    const std::size_t element_size,
    const std::size_t element_count,
    std::FILE* const stream
) noexcept {
    const auto original = LoadFunction<FreadFunction>(&g_original_fread);
    if (original == nullptr) {
        errno = EINVAL;
        return 0U;
    }
    CacheArchiveKind archive = CacheArchiveKind::none;
    std::uint64_t offset = kUnknownOffset;
    const bool tracked = SnapshotFile(stream, &archive, &offset);
    const std::uint64_t started = tracked ? QueryCounter() : 0U;
    const std::size_t result = original(buffer, element_size, element_count, stream);
    const int saved_errno = errno;
    if (tracked) {
        const std::uint64_t completed = QueryCounter();
        const std::uint64_t bytes = SaturatingProduct(result, element_size);
        const std::uint64_t requested = SaturatingProduct(element_count, element_size);
        AdvanceFile(stream, bytes);
        InterlockedIncrement64(&g_storage->header.cache_read_count);
        InterlockedAdd64(
            &g_storage->header.cache_read_bytes,
            static_cast<LONG64>(bytes > static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max())
                ? std::numeric_limits<LONG64>::max()
                : bytes)
        );
        const std::uint64_t duration = completed >= started ? completed - started : 0U;
        if (AggregateProfileSelected()) {
            AddAggregateCacheRead(bytes, duration);
        } else {
            Publish(
                kPerformanceCacheReadKind,
                kPerformanceStdioIoFlag | (result == element_count ? kPerformanceSuccessFlag : 0U),
                started,
                duration,
                archive,
                bytes,
                offset,
                requested,
                result == element_count ? ERROR_SUCCESS : ERROR_READ_FAULT,
                0U,
                0U
            );
        }
        g_loader_context = {completed, archive};
    }
    errno = saved_errno;
    return result;
}

int __cdecl TelemetryFseek(
    std::FILE* const stream,
    const long offset,
    const int origin
) noexcept {
    const auto original = LoadFunction<FseekFunction>(&g_original_fseek);
    if (original == nullptr) {
        errno = EINVAL;
        return -1;
    }
    const int result = original(stream, offset, origin);
    const int saved_errno = errno;
    if (result == 0) {
        AcquireSRWLockExclusive(&g_stream_lock);
        TrackedFile* const entry = FindTracked(g_files, stream);
        if (entry != nullptr) {
            if (origin == SEEK_SET && offset >= 0) {
                entry->offset = static_cast<std::uint64_t>(offset);
            } else if (origin == SEEK_CUR && entry->offset != kUnknownOffset) {
                const std::int64_t candidate = static_cast<std::int64_t>(entry->offset)
                    + static_cast<std::int64_t>(offset);
                entry->offset = candidate >= 0
                    ? static_cast<std::uint64_t>(candidate)
                    : kUnknownOffset;
            } else {
                entry->offset = kUnknownOffset;
            }
        }
        ReleaseSRWLockExclusive(&g_stream_lock);
    }
    errno = saved_errno;
    return result;
}

int __cdecl TelemetryFclose(std::FILE* const stream) noexcept {
    const auto original = LoadFunction<FcloseFunction>(&g_original_fclose);
    if (original == nullptr) {
        errno = EINVAL;
        return EOF;
    }
    RemoveTracked(g_files, stream);
    return original(stream);
}

void PublishTexture(
    const std::uint32_t kind,
    const std::uint64_t started,
    const std::uint64_t completed,
    const unsigned int target,
    const int level,
    const int width,
    const int height,
    const int internal_format,
    const unsigned int format,
    const unsigned int type,
    const void* const pixels
) noexcept {
    const std::uint64_t bytes = EstimateTextureUploadBytes(width, height, format, type);
    const std::uint64_t frequency = g_storage->header.qpc_frequency;
    std::uint64_t pipeline_gap = 0U;
    CacheArchiveKind archive = CacheArchiveKind::none;
    if (
        g_loader_context.completed_qpc != 0U
        && started >= g_loader_context.completed_qpc
        && frequency > 0U
        && started - g_loader_context.completed_qpc
            <= SaturatingProduct(frequency, kMaximumPipelineGapSeconds)
    ) {
        pipeline_gap = started - g_loader_context.completed_qpc;
        archive = g_loader_context.archive;
    }
    g_loader_context = {};
    InterlockedIncrement64(&g_storage->header.texture_upload_count);
    InterlockedAdd64(
        &g_storage->header.texture_upload_bytes,
        static_cast<LONG64>(bytes > static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max())
            ? std::numeric_limits<LONG64>::max()
            : bytes)
    );
    const std::uint64_t duration = completed >= started ? completed - started : 0U;
    if (AggregateProfileSelected()) {
        g_loader_context = {};
        AddAggregateTextureUpload(bytes, duration);
        return;
    }
    const std::uint64_t dimensions = static_cast<std::uint32_t>(width)
        | static_cast<std::uint64_t>(static_cast<std::uint32_t>(height)) << 32U;
    const std::uint64_t formats = static_cast<std::uint32_t>(internal_format)
        | static_cast<std::uint64_t>(format) << 32U;
    const std::uint64_t target_level_type = static_cast<std::uint64_t>(target)
        | static_cast<std::uint64_t>(static_cast<std::uint16_t>(level)) << 32U
        | static_cast<std::uint64_t>(type & 0xFFFFU) << 48U;
    Publish(
        kind,
        kPerformanceSuccessFlag | (pixels != nullptr ? kPerformancePixelsPresentFlag : 0U),
        started,
        duration,
        archive,
        bytes,
        dimensions,
        formats,
        target_level_type,
        0U,
        pipeline_gap
    );
}

void APIENTRY TelemetryTexImage2D(
    const unsigned int target,
    const int level,
    const int internal_format,
    const int width,
    const int height,
    const int border,
    const unsigned int format,
    const unsigned int type,
    const void* const pixels
) noexcept {
    const auto original = LoadFunction<GlTexImage2DFunction>(&g_original_tex_image_2d);
    if (original == nullptr) {
        return;
    }
    const std::uint64_t started = QueryCounter();
    original(target, level, internal_format, width, height, border, format, type, pixels);
    const std::uint64_t completed = QueryCounter();
    PublishTexture(
        kPerformanceTextureImageKind,
        started,
        completed,
        target,
        level,
        width,
        height,
        internal_format,
        format,
        type,
        pixels
    );
}

void APIENTRY TelemetryTexSubImage2D(
    const unsigned int target,
    const int level,
    const int x_offset,
    const int y_offset,
    const int width,
    const int height,
    const unsigned int format,
    const unsigned int type,
    const void* const pixels
) noexcept {
    const auto original = LoadFunction<GlTexSubImage2DFunction>(&g_original_tex_sub_image_2d);
    if (original == nullptr) {
        return;
    }
    const std::uint64_t started = QueryCounter();
    original(target, level, x_offset, y_offset, width, height, format, type, pixels);
    const std::uint64_t completed = QueryCounter();
    PublishTexture(
        kPerformanceTextureSubImageKind,
        started,
        completed,
        target,
        level,
        width,
        height,
        0,
        format,
        type,
        pixels
    );
}

bool RestoreHook(HookPlan& plan) noexcept {
    if (plan.slot == nullptr) {
        return true;
    }
    if (plan.original == nullptr) {
        return false;
    }
    const std::uintptr_t original = reinterpret_cast<std::uintptr_t>(plan.original);
    const std::uintptr_t replacement = reinterpret_cast<std::uintptr_t>(plan.replacement);
    if (original > UINT32_MAX || replacement > UINT32_MAX) {
        return false;
    }
    if (ReplaceImportAddressSlot(
            plan.slot,
            static_cast<std::uint32_t>(replacement),
            static_cast<std::uint32_t>(original)
        ) != ERROR_SUCCESS) {
        return false;
    }
    *plan.slot_storage = nullptr;
    return true;
}

void ClearOriginalFunctions() noexcept {
    InterlockedExchangePointer(&g_original_create_file_a, nullptr);
    InterlockedExchangePointer(&g_original_read_file, nullptr);
    InterlockedExchangePointer(&g_original_set_file_pointer, nullptr);
    InterlockedExchangePointer(&g_original_close_handle, nullptr);
    InterlockedExchangePointer(&g_original_fopen, nullptr);
    InterlockedExchangePointer(&g_original_wfopen, nullptr);
    InterlockedExchangePointer(&g_original_fread, nullptr);
    InterlockedExchangePointer(&g_original_fseek, nullptr);
    InterlockedExchangePointer(&g_original_fclose, nullptr);
    InterlockedExchangePointer(&g_original_tex_image_2d, nullptr);
    InterlockedExchangePointer(&g_original_tex_sub_image_2d, nullptr);
}

std::array<HookPlan, kPerformanceHookCount> HookPlans() noexcept {
    return {{
        {nullptr, "KERNEL32.dll", L"KERNEL32.dll", "CreateFileA", reinterpret_cast<PVOID>(&TelemetryCreateFileA), nullptr, nullptr, &g_original_create_file_a, &g_hook_slots[1], kPerformanceCacheReadCapability},
        {nullptr, "KERNEL32.dll", L"KERNEL32.dll", "ReadFile", reinterpret_cast<PVOID>(&TelemetryReadFile), nullptr, nullptr, &g_original_read_file, &g_hook_slots[2], kPerformanceCacheReadCapability},
        {nullptr, "KERNEL32.dll", L"KERNEL32.dll", "SetFilePointer", reinterpret_cast<PVOID>(&TelemetrySetFilePointer), nullptr, nullptr, &g_original_set_file_pointer, &g_hook_slots[3], kPerformanceCacheReadCapability},
        {nullptr, "KERNEL32.dll", L"KERNEL32.dll", "CloseHandle", reinterpret_cast<PVOID>(&TelemetryCloseHandle), nullptr, nullptr, &g_original_close_handle, &g_hook_slots[4], kPerformanceCacheReadCapability},
        {nullptr, "MSVCRT.dll", L"MSVCRT.dll", "fopen", reinterpret_cast<PVOID>(&TelemetryFopen), nullptr, nullptr, &g_original_fopen, &g_hook_slots[5], kPerformanceCacheReadCapability},
        {nullptr, "MSVCRT.dll", L"MSVCRT.dll", "_wfopen", reinterpret_cast<PVOID>(&TelemetryWfopen), nullptr, nullptr, &g_original_wfopen, &g_hook_slots[6], kPerformanceCacheReadCapability},
        {nullptr, "MSVCRT.dll", L"MSVCRT.dll", "fread", reinterpret_cast<PVOID>(&TelemetryFread), nullptr, nullptr, &g_original_fread, &g_hook_slots[7], kPerformanceCacheReadCapability},
        {nullptr, "MSVCRT.dll", L"MSVCRT.dll", "fseek", reinterpret_cast<PVOID>(&TelemetryFseek), nullptr, nullptr, &g_original_fseek, &g_hook_slots[8], kPerformanceCacheReadCapability},
        {nullptr, "MSVCRT.dll", L"MSVCRT.dll", "fclose", reinterpret_cast<PVOID>(&TelemetryFclose), nullptr, nullptr, &g_original_fclose, &g_hook_slots[9], kPerformanceCacheReadCapability},
        {nullptr, "OPENGL32.dll", L"OPENGL32.dll", "glTexImage2D", reinterpret_cast<PVOID>(&TelemetryTexImage2D), nullptr, nullptr, &g_original_tex_image_2d, &g_hook_slots[10], kPerformanceTextureUploadCapability},
        {nullptr, "OPENGL32.dll", L"OPENGL32.dll", "glTexSubImage2D", reinterpret_cast<PVOID>(&TelemetryTexSubImage2D), nullptr, nullptr, &g_original_tex_sub_image_2d, &g_hook_slots[11], kPerformanceTextureUploadCapability},
        {L"Core.dll", "KERNEL32.dll", L"KERNEL32.dll", "CloseHandle", reinterpret_cast<PVOID>(&TelemetryCloseHandle), nullptr, nullptr, &g_original_close_handle, &g_hook_slots[12], kPerformanceCacheReadCapability},
        {L"Core.dll", "MSVCRT.dll", L"MSVCRT.dll", "fopen", reinterpret_cast<PVOID>(&TelemetryFopen), nullptr, nullptr, &g_original_fopen, &g_hook_slots[13], kPerformanceCacheReadCapability},
        {L"Core.dll", "MSVCRT.dll", L"MSVCRT.dll", "fread", reinterpret_cast<PVOID>(&TelemetryFread), nullptr, nullptr, &g_original_fread, &g_hook_slots[14], kPerformanceCacheReadCapability},
        {L"Core.dll", "MSVCRT.dll", L"MSVCRT.dll", "fseek", reinterpret_cast<PVOID>(&TelemetryFseek), nullptr, nullptr, &g_original_fseek, &g_hook_slots[15], kPerformanceCacheReadCapability},
        {L"Core.dll", "MSVCRT.dll", L"MSVCRT.dll", "fclose", reinterpret_cast<PVOID>(&TelemetryFclose), nullptr, nullptr, &g_original_fclose, &g_hook_slots[16], kPerformanceCacheReadCapability},
        {L"DFEngine.dll", "KERNEL32.dll", L"KERNEL32.dll", "CreateFileA", reinterpret_cast<PVOID>(&TelemetryCreateFileA), nullptr, nullptr, &g_original_create_file_a, &g_hook_slots[17], kPerformanceCacheReadCapability},
        {L"DFEngine.dll", "KERNEL32.dll", L"KERNEL32.dll", "ReadFile", reinterpret_cast<PVOID>(&TelemetryReadFile), nullptr, nullptr, &g_original_read_file, &g_hook_slots[18], kPerformanceCacheReadCapability},
        {L"DFEngine.dll", "KERNEL32.dll", L"KERNEL32.dll", "SetFilePointer", reinterpret_cast<PVOID>(&TelemetrySetFilePointer), nullptr, nullptr, &g_original_set_file_pointer, &g_hook_slots[19], kPerformanceCacheReadCapability},
        {L"DFEngine.dll", "KERNEL32.dll", L"KERNEL32.dll", "CloseHandle", reinterpret_cast<PVOID>(&TelemetryCloseHandle), nullptr, nullptr, &g_original_close_handle, &g_hook_slots[20], kPerformanceCacheReadCapability},
    }};
}

DWORD InstallHooks(const std::uint32_t capability_flags) noexcept {
    static_assert(sizeof(void*) == sizeof(std::uint32_t));
    auto plans = HookPlans();
    for (HookPlan& plan : plans) {
        if ((plan.capability & capability_flags) == 0U) {
            continue;
        }
        const HMODULE image_module = GetModuleHandleW(plan.image_module_name);
        const HMODULE api_module = GetModuleHandleW(plan.api_module_name);
        if (image_module == nullptr || api_module == nullptr) {
            return ERROR_MOD_NOT_FOUND;
        }
        const auto* const dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(image_module);
        if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) {
            return ERROR_BAD_EXE_FORMAT;
        }
        const auto* const nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(
            reinterpret_cast<const std::uint8_t*>(image_module) + dos->e_lfanew
        );
        if (
            nt->Signature != IMAGE_NT_SIGNATURE
            || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
        ) {
            return ERROR_BAD_EXE_FORMAT;
        }
        plan.slot = FindImportAddressSlot(
            reinterpret_cast<std::uint8_t*>(image_module),
            nt->OptionalHeader.SizeOfImage,
            plan.import_library_name,
            plan.symbol_name
        );
        plan.original = reinterpret_cast<PVOID>(GetProcAddress(api_module, plan.symbol_name));
        const std::uintptr_t original = reinterpret_cast<std::uintptr_t>(plan.original);
        const std::uintptr_t replacement = reinterpret_cast<std::uintptr_t>(plan.replacement);
        if (
            plan.slot == nullptr
            || plan.original == nullptr
            || original > UINT32_MAX
            || replacement > UINT32_MAX
            || *plan.slot != static_cast<std::uint32_t>(original)
        ) {
            return ERROR_PROC_NOT_FOUND;
        }
    }
    for (std::size_t left = 0U; left < plans.size(); ++left) {
        if ((plans[left].capability & capability_flags) == 0U) {
            continue;
        }
        for (std::size_t right = left + 1U; right < plans.size(); ++right) {
            if (
                (plans[right].capability & capability_flags) != 0U
                && plans[left].slot == plans[right].slot
            ) {
                return ERROR_INVALID_DATA;
            }
        }
    }
    std::array<std::size_t, kPerformanceHookCount> installed_indices{};
    std::size_t installed = 0U;
    for (std::size_t plan_index = 0U; plan_index < plans.size(); ++plan_index) {
        HookPlan& plan = plans[plan_index];
        if ((plan.capability & capability_flags) == 0U) {
            continue;
        }
        InterlockedExchangePointer(plan.original_storage, plan.original);
        const DWORD result = ReplaceImportAddressSlot(
            plan.slot,
            static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(plan.original)),
            static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(plan.replacement))
        );
        if (result != ERROR_SUCCESS) {
            bool restored = true;
            for (std::size_t index = installed; index > 0U; --index) {
                HookPlan& installed_plan = plans[installed_indices[index - 1U]];
                if (RestoreHook(installed_plan)) {
                    InterlockedDecrement(&g_storage->header.active_hook_count);
                } else {
                    restored = false;
                }
            }
            if (restored) {
                ClearOriginalFunctions();
            }
            return result;
        }
        *plan.slot_storage = plan.slot;
        installed_indices[installed++] = plan_index;
        InterlockedIncrement(&g_storage->header.active_hook_count);
    }
    return ERROR_SUCCESS;
}

void CleanupMapping() noexcept {
    if (g_storage != nullptr) {
        UnmapViewOfFile(g_storage);
        g_storage = nullptr;
    }
    if (g_mapping != nullptr) {
        CloseHandle(g_mapping);
        g_mapping = nullptr;
    }
}

}  // namespace

CacheArchiveKind ClassifyCacheArchivePath(const char* const file_name) noexcept {
    return ClassifyCacheName(file_name);
}

CacheArchiveKind ClassifyCacheArchivePath(const wchar_t* const file_name) noexcept {
    return ClassifyCacheName(file_name);
}

std::uint64_t EstimateTextureUploadBytes(
    const int width,
    const int height,
    const unsigned int format,
    const unsigned int type
) noexcept {
    return EstimateTextureBytes(width, height, format, type);
}

DWORD SelectPerformanceTelemetryProfile(
    const wchar_t* const configured_value,
    PerformanceTelemetryProfile* const profile
) noexcept {
    if (profile == nullptr) {
        return ERROR_INVALID_PARAMETER;
    }
    if (
        configured_value == nullptr
        || configured_value[0] == L'\0'
        || lstrcmpW(configured_value, L"frame") == 0
    ) {
        *profile = PerformanceTelemetryProfile::frame;
        return ERROR_SUCCESS;
    }
    if (lstrcmpW(configured_value, L"off") == 0) {
        *profile = PerformanceTelemetryProfile::disabled;
        return ERROR_SUCCESS;
    }
    if (lstrcmpW(configured_value, L"full") == 0) {
        *profile = PerformanceTelemetryProfile::full;
        return ERROR_SUCCESS;
    }
    if (lstrcmpW(configured_value, L"aggregate") == 0) {
        *profile = PerformanceTelemetryProfile::aggregate;
        return ERROR_SUCCESS;
    }
    return ERROR_INVALID_DATA;
}

DWORD FormatPerformanceTelemetryMappingName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"Local\\ShadowbaneLab.Extension.Performance.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    if (SUCCEEDED(result)) {
        return ERROR_SUCCESS;
    }
    return HRESULT_FACILITY(result) == FACILITY_WIN32
        ? HRESULT_CODE(result)
        : ERROR_GEN_FAILURE;
}

DWORD StartPerformanceTelemetry(
    const ProcessIdentity& identity,
    const PerformanceTelemetryProfile profile
) noexcept {
    if (
        identity.process_id == 0U
        || identity.creation_filetime_utc == 0U
        || (
            profile != PerformanceTelemetryProfile::frame
            && profile != PerformanceTelemetryProfile::full
            && profile != PerformanceTelemetryProfile::aggregate
        )
        || g_mapping != nullptr
        || g_storage != nullptr
    ) {
        return ERROR_INVALID_STATE;
    }
    wchar_t mapping_name[kKernelObjectNameCapacity]{};
    DWORD result = FormatPerformanceTelemetryMappingName(
        identity,
        mapping_name,
        kKernelObjectNameCapacity
    );
    if (result != ERROR_SUCCESS) {
        return result;
    }
    g_mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0U,
        static_cast<DWORD>(sizeof(PerformanceTelemetryStorage)),
        mapping_name
    );
    if (g_mapping == nullptr) {
        return GetLastError();
    }
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(g_mapping);
        g_mapping = nullptr;
        return ERROR_ALREADY_EXISTS;
    }
    g_storage = static_cast<PerformanceTelemetryStorage*>(MapViewOfFile(
        g_mapping,
        FILE_MAP_READ | FILE_MAP_WRITE,
        0U,
        0U,
        sizeof(PerformanceTelemetryStorage)
    ));
    if (g_storage == nullptr) {
        result = GetLastError();
        CleanupMapping();
        return result;
    }
    LARGE_INTEGER frequency{};
    LARGE_INTEGER started{};
    if (
        QueryPerformanceFrequency(&frequency) == FALSE
        || QueryPerformanceCounter(&started) == FALSE
        || frequency.QuadPart <= 0
        || started.QuadPart <= 0
    ) {
        result = GetLastError();
        CleanupMapping();
        return result != ERROR_SUCCESS ? result : ERROR_INVALID_DATA;
    }
    ZeroMemory(g_storage, sizeof(PerformanceTelemetryStorage));
    std::memcpy(
        g_storage->header.magic,
        kPerformanceTelemetryMagic,
        sizeof(kPerformanceTelemetryMagic)
    );
    g_storage->header.schema_version = kPerformanceTelemetrySchemaVersion;
    g_storage->header.header_size = kPerformanceTelemetryHeaderSize;
    g_storage->header.slot_size = kPerformanceTelemetrySlotSize;
    g_storage->header.capacity = kPerformanceTelemetryCapacity;
    g_storage->header.process_id = identity.process_id;
    const std::uint32_t capability_flags = profile == PerformanceTelemetryProfile::aggregate
        ? kPerformanceAggregateCapability
        : profile == PerformanceTelemetryProfile::full
            ? kPerformanceFullCapability
            : kPerformanceFrameCapability;
    g_storage->header.capability_flags = capability_flags;
    g_storage->header.process_creation_filetime_utc = identity.creation_filetime_utc;
    g_storage->header.qpc_frequency = static_cast<std::uint64_t>(frequency.QuadPart);
    g_storage->header.started_qpc = static_cast<std::uint64_t>(started.QuadPart);
    g_previous_present_qpc = 0U;
    InterlockedExchange(&g_profile, static_cast<LONG>(profile));
    MemoryBarrier();
    result = InstallHooks(capability_flags);
    if (result != ERROR_SUCCESS) {
        StopPerformanceTelemetry();
    }
    return result;
}

std::uint64_t BeginPerformancePresent() noexcept {
    if (g_storage == nullptr) {
        return 0U;
    }
    const std::uint64_t started_qpc = QueryCounter();
    if (started_qpc == 0U) {
        return 0U;
    }
    if (AggregateProfileSelected()) {
        AcquireSRWLockExclusive(&g_aggregate_lock);
        g_pending_frame_totals = g_frame_totals;
        g_frame_totals = {};
        ReleaseSRWLockExclusive(&g_aggregate_lock);
    }
    return started_qpc;
}

void ObservePerformancePresent(
    const std::uint64_t started_qpc,
    const bool succeeded
) noexcept {
    if (g_storage == nullptr || started_qpc == 0U) {
        return;
    }
    const std::uint64_t completed_qpc = QueryCounter();
    const std::uint64_t duration_qpc = completed_qpc >= started_qpc
        ? completed_qpc - started_qpc
        : 0U;
    const std::uint64_t frame_interval_qpc = g_previous_present_qpc != 0U
        && started_qpc >= g_previous_present_qpc
            ? started_qpc - g_previous_present_qpc
            : 0U;
    g_previous_present_qpc = started_qpc;
    InterlockedIncrement64(&g_storage->header.frame_count);
    const std::uint64_t frequency = g_storage->header.qpc_frequency;
    const bool slow = frequency > 0U
        && frame_interval_qpc >= SaturatingProduct(
            frequency,
            kSlowFrameMicroseconds
        ) / 1'000'000U;
    if (slow) {
        InterlockedIncrement64(&g_storage->header.slow_frame_count);
    }
    if (AggregateProfileSelected()) {
        FrameTotals totals{};
        AcquireSRWLockExclusive(&g_aggregate_lock);
        totals = g_pending_frame_totals;
        g_pending_frame_totals = {};
        ReleaseSRWLockExclusive(&g_aggregate_lock);
        Publish(
            kPerformanceFrameSummaryKind,
            succeeded ? kPerformanceSuccessFlag : 0U,
            started_qpc,
            duration_qpc,
            CacheArchiveKind::none,
            totals.cache_read_bytes,
            totals.cache_read_count,
            totals.cache_read_duration_qpc,
            totals.texture_upload_count,
            frame_interval_qpc,
            totals.texture_upload_duration_qpc,
            totals.texture_upload_bytes
        );
    } else if (slow) {
        Publish(
            kPerformanceFrameGapKind,
            succeeded ? kPerformanceSuccessFlag : 0U,
            started_qpc,
            duration_qpc,
            CacheArchiveKind::none,
            0U,
            0U,
            0U,
            0U,
            frame_interval_qpc,
            0U
        );
    }
}

void StopPerformanceTelemetry() noexcept {
    auto plans = HookPlans();
    bool restored = true;
    for (std::size_t index = plans.size(); index > 0U; --index) {
        HookPlan& plan = plans[index - 1U];
        plan.slot = *plan.slot_storage;
        plan.original = LoadFunction<PVOID>(plan.original_storage);
        const bool was_installed = plan.slot != nullptr;
        if (!RestoreHook(plan)) {
            restored = false;
        } else if (was_installed && g_storage != nullptr) {
            InterlockedDecrement(&g_storage->header.active_hook_count);
        }
    }
    if (!restored) {
        return;
    }
    ClearOriginalFunctions();
    AcquireSRWLockExclusive(&g_stream_lock);
    g_handles = {};
    g_files = {};
    ReleaseSRWLockExclusive(&g_stream_lock);
    AcquireSRWLockExclusive(&g_aggregate_lock);
    g_frame_totals = {};
    g_pending_frame_totals = {};
    ReleaseSRWLockExclusive(&g_aggregate_lock);
    g_previous_present_qpc = 0U;
    InterlockedExchange(&g_profile, static_cast<LONG>(PerformanceTelemetryProfile::disabled));
    CleanupMapping();
}

}  // namespace wonderbane::extension
