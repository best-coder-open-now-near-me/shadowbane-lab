#include "graphics_status.h"

#include "extension_api.h"
#include "graphics_control.h"
#include "scene_frame.h"

#include <KnownFolders.h>
#include <ShlObj.h>
#include <bcrypt.h>
#include <strsafe.h>

#include <array>
#include <cctype>
#include <cmath>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {

constexpr wchar_t kProductDirectory[] = L"ShadowbaneLab";
constexpr wchar_t kExtensionDirectory[] = L"client-extension";
constexpr char kProducerId[] = "wonderbane-extension.graphics";
constexpr char kExtensionVersion[] = "1.6.10";
constexpr std::size_t kPathCapacity = WONDERBANE_EXTENSION_HEARTBEAT_PATH_CAPACITY;
constexpr std::size_t kExecutablePathUtf8Capacity = kPathCapacity * 4U;
constexpr std::size_t kEscapedPathCapacity = kExecutablePathUtf8Capacity * 2U + 3U;
constexpr std::size_t kDriverStringCapacity = 256U;
constexpr std::size_t kEscapedDriverStringCapacity = kDriverStringCapacity * 2U + 3U;
constexpr std::size_t kFrameTimingSampleCapacity = 1024U;
constexpr std::size_t kFrameTimingJsonCapacity = 64U * 1024U;
constexpr std::size_t kCameraStateSampleCapacity = 256U;
constexpr std::size_t kCameraStateJsonCapacity = 256U * 1024U;
constexpr std::size_t kJsonCapacity = 384U * 1024U;
constexpr std::size_t kDepthEdgeReasonCapacity = 128U;
constexpr std::size_t kEscapedDepthEdgeReasonCapacity =
    kDepthEdgeReasonCapacity * 2U + 3U;
constexpr std::size_t kControlNameUtf8Capacity = 512U;
constexpr std::size_t kEscapedControlNameCapacity = kControlNameUtf8Capacity * 2U + 3U;
constexpr DWORD kPublishIntervalMilliseconds = 2'000U;
constexpr DWORD kWorkerStopTimeoutMilliseconds = 5'000U;
constexpr std::size_t kHashReadCapacity = 64U * 1024U;
constexpr ULONG kMaximumHashObjectBytes = 1024U * 1024U;
constexpr unsigned int kGlVersion = 0x1F02U;
constexpr unsigned int kGlExtensions = 0x1F03U;
constexpr unsigned int kGlShadingLanguageVersion = 0x8B8CU;
constexpr unsigned int kGlDepthBits = 0x0D56U;
constexpr unsigned int kGlViewport = 0x0BA2U;

using GlGetString = const unsigned char*(APIENTRY*)(unsigned int name);
using GlGetIntegerv = void(APIENTRY*)(unsigned int name, int* values);
using WglGetCurrentContext = HGLRC(WINAPI*)();

struct GraphicsContextSnapshot {
    std::uintptr_t context = 0U;
    bool observed = false;
    char gl_version[kDriverStringCapacity]{};
    char glsl_version[kDriverStringCapacity]{};
    int depth_bits = 0;
    bool depth_texture_supported = false;
    bool framebuffer_object_supported = false;
    int viewport[4U]{};
};

struct FrameTimingSample {
    std::uint64_t sequence = 0U;
    std::int64_t counter = 0;
};

struct CameraStateSample {
    std::uint64_t sequence = 0U;
    std::uint64_t present_sequence = 0U;
    std::int64_t counter = 0;
    GraphicsCameraState state{};
};

struct GraphicsStatusState {
    bool configured = false;
    char runtime_profile[32U]{};
    char library_name[64U]{};
    char symbol_name[128U]{};
    std::uint32_t iat_rva = 0U;
    std::uint64_t call_count = 0U;
    ULONGLONG last_publish_signal_tick = 0U;
    std::int64_t performance_counter_frequency = 0;
    std::uint64_t timing_query_failure_count = 0U;
    std::array<FrameTimingSample, kFrameTimingSampleCapacity> frame_timing_samples{};
    std::uint64_t camera_sample_sequence = 0U;
    std::uint64_t camera_producer_drop_count = 0U;
    std::array<CameraStateSample, kCameraStateSampleCapacity> camera_state_samples{};
    bool pending_camera_valid = false;
    bool pending_camera_ambiguous = false;
    std::uint64_t pending_camera_present_sequence = 0U;
    CameraStateSample pending_camera{};
    GraphicsContextSnapshot graphics_context{};
    std::uint64_t depth_edge_composite_count = 0U;
    bool depth_edge_failed = false;
    char depth_edge_failure_reason[kDepthEdgeReasonCapacity]{};
    std::uint64_t scene_color_capture_count = 0U;
    bool scene_color_failed = false;
    char scene_color_failure_reason[kDepthEdgeReasonCapacity]{};
    std::uint64_t classified_frame_count = 0U;
    SceneFrameState latest_scene_frame{};
    std::array<std::uint64_t, kDrawLayerCount> classified_draw_counts{};
    std::array<std::uint64_t, kDrawClassificationReasonCount>
        classification_reason_counts{};
    std::uint64_t scene_boundary_count = 0U;
    std::uint64_t late_world_draw_count = 0U;
    std::uint64_t fixed_function_refresh_count = 0U;
};

struct PublisherSnapshot {
    DWORD process_id = 0U;
    std::uint64_t process_creation_filetime_utc = 0U;
    wchar_t executable_path[kPathCapacity]{};
    char executable_sha256[65U]{};
    wchar_t final_path[kPathCapacity]{};
    GraphicsStatusState status{};
    std::int64_t snapshot_counter = 0;
    std::uint64_t snapshot_filetime_utc = 0U;
};

SRWLOCK g_state_lock = SRWLOCK_INIT;
volatile LONG g_started = 0;
HANDLE g_stop_event = nullptr;
HANDLE g_wake_event = nullptr;
HANDLE g_ready_event = nullptr;
HANDLE g_worker_thread = nullptr;
volatile LONG g_initial_publish_result = ERROR_IO_PENDING;
DWORD g_process_id = 0U;
std::uint64_t g_process_creation_filetime_utc = 0U;
wchar_t g_executable_path[kPathCapacity]{};
char g_executable_sha256[65U]{};
wchar_t g_graphics_status_path[kPathCapacity]{};
GraphicsStatusState g_status{};

DWORD HResultToWin32(const HRESULT result) noexcept {
    return HRESULT_FACILITY(result) == FACILITY_WIN32
        ? HRESULT_CODE(result)
        : ERROR_GEN_FAILURE;
}

std::uint64_t FileTimeValue(const FILETIME value) noexcept {
    ULARGE_INTEGER combined{};
    combined.LowPart = value.dwLowDateTime;
    combined.HighPart = value.dwHighDateTime;
    return combined.QuadPart;
}

void SaturatingAdd(
    std::uint64_t* const destination,
    const std::uint64_t value
) noexcept {
    if (destination == nullptr) {
        return;
    }
    *destination = *destination > UINT64_MAX - value
        ? UINT64_MAX
        : *destination + value;
}

bool NtSucceeded(const NTSTATUS status) noexcept {
    return status >= 0;
}

DWORD RequireOrdinaryDirectory(const wchar_t* const path) noexcept {
    if (CreateDirectoryW(path, nullptr) != FALSE) {
        return ERROR_SUCCESS;
    }
    const DWORD creation_error = GetLastError();
    if (creation_error != ERROR_ALREADY_EXISTS) {
        return creation_error;
    }
    const DWORD attributes = GetFileAttributesW(path);
    if (attributes == INVALID_FILE_ATTRIBUTES) {
        return GetLastError();
    }
    if ((attributes & FILE_ATTRIBUTE_DIRECTORY) == 0U) {
        return ERROR_DIRECTORY;
    }
    if ((attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0U) {
        return ERROR_REPARSE_TAG_MISMATCH;
    }
    return ERROR_SUCCESS;
}

DWORD CombinePath(
    wchar_t* const destination,
    const std::size_t destination_capacity,
    const wchar_t* const parent,
    const wchar_t* const leaf
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"%s\\%s",
        parent,
        leaf
    );
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

DWORD WriteAll(const HANDLE file, const char* const data, const DWORD length) noexcept {
    DWORD total_written = 0U;
    while (total_written < length) {
        DWORD written = 0U;
        if (WriteFile(
                file,
                data + total_written,
                length - total_written,
                &written,
                nullptr
            ) == FALSE) {
            return GetLastError();
        }
        if (written == 0U) {
            return ERROR_WRITE_FAULT;
        }
        total_written += written;
    }
    return ERROR_SUCCESS;
}

DWORD Sha256File(
    const wchar_t* const path,
    char* const hexadecimal,
    const std::size_t hexadecimal_capacity
) noexcept {
    if (path == nullptr || hexadecimal == nullptr || hexadecimal_capacity < 65U) {
        return ERROR_INVALID_PARAMETER;
    }
    const HANDLE file = CreateFileW(
        path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN,
        nullptr
    );
    if (file == INVALID_HANDLE_VALUE) {
        return GetLastError();
    }
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    UCHAR* hash_object = nullptr;
    DWORD result = ERROR_SUCCESS;
    ULONG object_bytes = 0U;
    ULONG property_bytes = 0U;
    NTSTATUS status = BCryptOpenAlgorithmProvider(
        &algorithm,
        BCRYPT_SHA256_ALGORITHM,
        nullptr,
        0U
    );
    if (!NtSucceeded(status)) {
        result = ERROR_GEN_FAILURE;
    }
    if (result == ERROR_SUCCESS) {
        status = BCryptGetProperty(
            algorithm,
            BCRYPT_OBJECT_LENGTH,
            reinterpret_cast<PUCHAR>(&object_bytes),
            sizeof(object_bytes),
            &property_bytes,
            0U
        );
        if (!NtSucceeded(status) || object_bytes == 0U
            || object_bytes > kMaximumHashObjectBytes) {
            result = ERROR_INVALID_DATA;
        }
    }
    if (result == ERROR_SUCCESS) {
        hash_object = static_cast<UCHAR*>(HeapAlloc(
            GetProcessHeap(),
            HEAP_ZERO_MEMORY,
            object_bytes
        ));
        if (hash_object == nullptr) {
            result = ERROR_NOT_ENOUGH_MEMORY;
        }
    }
    if (result == ERROR_SUCCESS) {
        status = BCryptCreateHash(
            algorithm,
            &hash,
            hash_object,
            object_bytes,
            nullptr,
            0U,
            0U
        );
        if (!NtSucceeded(status)) {
            result = ERROR_GEN_FAILURE;
        }
    }
    std::array<UCHAR, kHashReadCapacity> buffer{};
    while (result == ERROR_SUCCESS) {
        DWORD read = 0U;
        if (ReadFile(
                file,
                buffer.data(),
                static_cast<DWORD>(buffer.size()),
                &read,
                nullptr
            ) == FALSE) {
            result = GetLastError();
            break;
        }
        if (read == 0U) {
            break;
        }
        status = BCryptHashData(hash, buffer.data(), read, 0U);
        if (!NtSucceeded(status)) {
            result = ERROR_GEN_FAILURE;
        }
    }
    std::array<UCHAR, 32U> digest{};
    if (result == ERROR_SUCCESS) {
        status = BCryptFinishHash(
            hash,
            digest.data(),
            static_cast<ULONG>(digest.size()),
            0U
        );
        if (!NtSucceeded(status)) {
            result = ERROR_GEN_FAILURE;
        }
    }
    if (result == ERROR_SUCCESS) {
        constexpr char kHex[] = "0123456789abcdef";
        for (std::size_t index = 0U; index < digest.size(); ++index) {
            hexadecimal[index * 2U] = kHex[digest[index] >> 4U];
            hexadecimal[index * 2U + 1U] = kHex[digest[index] & 0x0FU];
        }
        hexadecimal[64U] = '\0';
    }
    if (hash != nullptr) {
        BCryptDestroyHash(hash);
    }
    if (hash_object != nullptr) {
        SecureZeroMemory(hash_object, object_bytes);
        HeapFree(GetProcessHeap(), 0U, hash_object);
    }
    if (algorithm != nullptr) {
        BCryptCloseAlgorithmProvider(algorithm, 0U);
    }
    CloseHandle(file);
    return result;
}

bool CopyDriverString(
    char* const destination,
    const std::size_t destination_capacity,
    const unsigned char* const source
) noexcept {
    if (destination == nullptr || destination_capacity == 0U) {
        return false;
    }
    destination[0] = '\0';
    if (source == nullptr) {
        return false;
    }
    return SUCCEEDED(StringCchCopyA(
        destination,
        destination_capacity,
        reinterpret_cast<const char*>(source)
    ));
}

GraphicsContextSnapshot QueryGraphicsContext() noexcept {
    GraphicsContextSnapshot snapshot{};
    const HMODULE opengl = GetModuleHandleW(L"OPENGL32.dll");
    if (opengl == nullptr) {
        return snapshot;
    }
    const auto get_current_context = reinterpret_cast<WglGetCurrentContext>(
        GetProcAddress(opengl, "wglGetCurrentContext")
    );
    const auto get_string = reinterpret_cast<GlGetString>(
        GetProcAddress(opengl, "glGetString")
    );
    const auto get_integerv = reinterpret_cast<GlGetIntegerv>(
        GetProcAddress(opengl, "glGetIntegerv")
    );
    if (get_current_context == nullptr || get_string == nullptr || get_integerv == nullptr) {
        return snapshot;
    }
    const HGLRC context = get_current_context();
    if (context == nullptr) {
        return snapshot;
    }
    snapshot.context = reinterpret_cast<std::uintptr_t>(context);
    snapshot.observed = true;
    CopyDriverString(
        snapshot.gl_version,
        std::size(snapshot.gl_version),
        get_string(kGlVersion)
    );
    CopyDriverString(
        snapshot.glsl_version,
        std::size(snapshot.glsl_version),
        get_string(kGlShadingLanguageVersion)
    );
    const auto* const extensions = reinterpret_cast<const char*>(
        get_string(kGlExtensions)
    );
    get_integerv(kGlDepthBits, &snapshot.depth_bits);
    get_integerv(kGlViewport, snapshot.viewport);
    snapshot.depth_texture_supported = IsGraphicsVersionAtLeast(
        snapshot.gl_version,
        1U,
        4U
    ) || HasGraphicsExtensionToken(extensions, "GL_ARB_depth_texture")
        || HasGraphicsExtensionToken(extensions, "GL_SGIX_depth_texture");
    snapshot.framebuffer_object_supported = IsGraphicsVersionAtLeast(
        snapshot.gl_version,
        3U,
        0U
    ) || HasGraphicsExtensionToken(extensions, "GL_ARB_framebuffer_object")
        || HasGraphicsExtensionToken(extensions, "GL_EXT_framebuffer_object");
    return snapshot;
}

bool Utf8Path(
    const wchar_t* const source,
    char* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (source == nullptr || destination == nullptr || destination_capacity == 0U
        || destination_capacity > INT_MAX) {
        return false;
    }
    return WideCharToMultiByte(
        CP_UTF8,
        WC_ERR_INVALID_CHARS,
        source,
        -1,
        destination,
        static_cast<int>(destination_capacity),
        nullptr,
        nullptr
    ) > 0;
}

bool JsonString(
    const char* const source,
    char* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (source == nullptr || destination == nullptr || destination_capacity < 3U) {
        return false;
    }
    constexpr char kHex[] = "0123456789abcdef";
    std::size_t output = 0U;
    destination[output++] = '"';
    for (std::size_t input = 0U; source[input] != '\0'; ++input) {
        const unsigned char value = static_cast<unsigned char>(source[input]);
        const char* escape = nullptr;
        if (value == static_cast<unsigned char>('"')) {
            escape = "\\\"";
        } else if (value == static_cast<unsigned char>('\\')) {
            escape = "\\\\";
        } else if (value == '\b') {
            escape = "\\b";
        } else if (value == '\f') {
            escape = "\\f";
        } else if (value == '\n') {
            escape = "\\n";
        } else if (value == '\r') {
            escape = "\\r";
        } else if (value == '\t') {
            escape = "\\t";
        }
        if (escape != nullptr) {
            if (output + 2U >= destination_capacity) {
                return false;
            }
            destination[output++] = escape[0];
            destination[output++] = escape[1];
        } else if (value < 0x20U) {
            if (output + 6U >= destination_capacity) {
                return false;
            }
            destination[output++] = '\\';
            destination[output++] = 'u';
            destination[output++] = '0';
            destination[output++] = '0';
            destination[output++] = kHex[value >> 4U];
            destination[output++] = kHex[value & 0x0FU];
        } else {
            if (output + 1U >= destination_capacity) {
                return false;
            }
            destination[output++] = static_cast<char>(value);
        }
    }
    if (output + 2U > destination_capacity) {
        return false;
    }
    destination[output++] = '"';
    destination[output] = '\0';
    return true;
}

bool JsonStringOrNull(
    const char* const source,
    char* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (source != nullptr && source[0] != '\0') {
        return JsonString(source, destination, destination_capacity);
    }
    return SUCCEEDED(StringCchCopyA(destination, destination_capacity, "null"));
}

PublisherSnapshot SnapshotState() noexcept {
    PublisherSnapshot snapshot{};
    AcquireSRWLockShared(&g_state_lock);
    snapshot.process_id = g_process_id;
    snapshot.process_creation_filetime_utc = g_process_creation_filetime_utc;
    StringCchCopyW(snapshot.executable_path, kPathCapacity, g_executable_path);
    StringCchCopyA(
        snapshot.executable_sha256,
        std::size(snapshot.executable_sha256),
        g_executable_sha256
    );
    StringCchCopyW(snapshot.final_path, kPathCapacity, g_graphics_status_path);
    snapshot.status = g_status;
    ReleaseSRWLockShared(&g_state_lock);
    LARGE_INTEGER counter{};
    QueryPerformanceCounter(&counter);
    snapshot.snapshot_counter = counter.QuadPart;
    FILETIME snapshot_time{};
    GetSystemTimePreciseAsFileTime(&snapshot_time);
    snapshot.snapshot_filetime_utc = FileTimeValue(snapshot_time);
    return snapshot;
}

DWORD FormatFrameTiming(
    const PublisherSnapshot& snapshot,
    char* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (destination == nullptr || destination_capacity == 0U) {
        return ERROR_INVALID_PARAMETER;
    }
    const std::uint64_t first_candidate = (
        snapshot.status.call_count > kFrameTimingSampleCapacity
            ? snapshot.status.call_count - kFrameTimingSampleCapacity + 1U
            : 1U
    );
    std::uint64_t oldest_sequence = 0U;
    std::size_t sample_count = 0U;
    for (
        std::uint64_t sequence = first_candidate;
        sequence <= snapshot.status.call_count;
        ++sequence
    ) {
        const FrameTimingSample& sample = snapshot.status.frame_timing_samples[
            static_cast<std::size_t>((sequence - 1U) % kFrameTimingSampleCapacity)
        ];
        if (sample.sequence == sequence) {
            if (oldest_sequence == 0U) {
                oldest_sequence = sequence;
            }
            ++sample_count;
        }
    }
    char* cursor = destination;
    std::size_t remaining = destination_capacity;
    HRESULT result = StringCchPrintfExA(
        cursor,
        remaining,
        &cursor,
        &remaining,
        0U,
        "{\"clock\":\"windows-query-performance-counter\","
        "\"counter_frequency_hz\":%lld,\"snapshot_counter\":%lld,"
        "\"snapshot_filetime_utc\":%llu,\"latest_present_sequence\":%llu,"
        "\"oldest_available_sequence\":%llu,\"sample_capacity\":%llu,"
        "\"sample_count\":%llu,\"timing_query_failure_count\":%llu,"
        "\"samples\":[",
        static_cast<long long>(snapshot.status.performance_counter_frequency),
        static_cast<long long>(snapshot.snapshot_counter),
        static_cast<unsigned long long>(snapshot.snapshot_filetime_utc),
        static_cast<unsigned long long>(snapshot.status.call_count),
        static_cast<unsigned long long>(oldest_sequence),
        static_cast<unsigned long long>(kFrameTimingSampleCapacity),
        static_cast<unsigned long long>(sample_count),
        static_cast<unsigned long long>(snapshot.status.timing_query_failure_count)
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    bool first_sample = true;
    for (
        std::uint64_t sequence = first_candidate;
        sequence <= snapshot.status.call_count;
        ++sequence
    ) {
        const FrameTimingSample& sample = snapshot.status.frame_timing_samples[
            static_cast<std::size_t>((sequence - 1U) % kFrameTimingSampleCapacity)
        ];
        if (sample.sequence != sequence) {
            continue;
        }
        result = StringCchPrintfExA(
            cursor,
            remaining,
            &cursor,
            &remaining,
            0U,
            "%s[%llu,%lld]",
            first_sample ? "" : ",",
            static_cast<unsigned long long>(sample.sequence),
            static_cast<long long>(sample.counter)
        );
        if (FAILED(result)) {
            return HResultToWin32(result);
        }
        first_sample = false;
    }
    result = StringCchCopyA(cursor, remaining, "]}");
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

DWORD FormatFloatArray(
    const float* const values,
    const std::size_t count,
    char* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (values == nullptr || count == 0U || destination == nullptr
        || destination_capacity < 3U) {
        return ERROR_INVALID_PARAMETER;
    }
    char* cursor = destination;
    std::size_t remaining = destination_capacity;
    HRESULT result = StringCchCopyExA(
        cursor, remaining, "[", &cursor, &remaining, 0U
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    for (std::size_t index = 0U; index < count; ++index) {
        if (!std::isfinite(values[index])) {
            return ERROR_INVALID_DATA;
        }
        result = StringCchPrintfExA(
            cursor,
            remaining,
            &cursor,
            &remaining,
            0U,
            "%s%.9g",
            index == 0U ? "" : ",",
            static_cast<double>(values[index])
        );
        if (FAILED(result)) {
            return HResultToWin32(result);
        }
    }
    result = StringCchCopyA(cursor, remaining, "]");
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

DWORD FormatCameraState(
    const PublisherSnapshot& snapshot,
    char* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (destination == nullptr || destination_capacity == 0U) {
        return ERROR_INVALID_PARAMETER;
    }
    const std::uint64_t latest_sequence = snapshot.status.camera_sample_sequence;
    const std::uint64_t first_candidate = (
        latest_sequence > kCameraStateSampleCapacity
            ? latest_sequence - kCameraStateSampleCapacity + 1U
            : 1U
    );
    std::uint64_t oldest_sequence = 0U;
    std::size_t sample_count = 0U;
    for (std::uint64_t sequence = first_candidate;
         sequence <= latest_sequence;
         ++sequence) {
        const CameraStateSample& sample = snapshot.status.camera_state_samples[
            static_cast<std::size_t>((sequence - 1U) % kCameraStateSampleCapacity)
        ];
        if (sample.sequence == sequence) {
            if (oldest_sequence == 0U) {
                oldest_sequence = sequence;
            }
            ++sample_count;
        }
    }
    char* cursor = destination;
    std::size_t remaining = destination_capacity;
    HRESULT result = StringCchPrintfExA(
        cursor,
        remaining,
        &cursor,
        &remaining,
        0U,
        "{\"schema_version\":1,\"clock\":\"windows-query-performance-counter\","
        "\"counter_frequency_hz\":%lld,"
        "\"source\":\"unique-base-model-view-per-present\","
        "\"mapping_authority\":\"runtime-observed-fixed-function-state\","
        "\"latest_sample_sequence\":%llu,\"oldest_available_sequence\":%llu,"
        "\"sample_capacity\":%llu,\"sample_count\":%llu,"
        "\"producer_drop_count\":%llu,\"samples\":[",
        static_cast<long long>(snapshot.status.performance_counter_frequency),
        static_cast<unsigned long long>(latest_sequence),
        static_cast<unsigned long long>(oldest_sequence),
        static_cast<unsigned long long>(kCameraStateSampleCapacity),
        static_cast<unsigned long long>(sample_count),
        static_cast<unsigned long long>(snapshot.status.camera_producer_drop_count)
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    bool first_sample = true;
    for (std::uint64_t sequence = first_candidate;
         sequence <= latest_sequence;
         ++sequence) {
        const CameraStateSample& sample = snapshot.status.camera_state_samples[
            static_cast<std::size_t>((sequence - 1U) % kCameraStateSampleCapacity)
        ];
        if (sample.sequence != sequence) {
            continue;
        }
        std::array<char, 128U> position{};
        std::array<char, 128U> forward{};
        std::array<char, 128U> up{};
        std::array<char, 512U> view{};
        std::array<char, 512U> projection{};
        DWORD format_result = FormatFloatArray(
            sample.state.position, 3U, position.data(), position.size()
        );
        if (format_result == ERROR_SUCCESS) {
            format_result = FormatFloatArray(
                sample.state.forward, 3U, forward.data(), forward.size()
            );
        }
        if (format_result == ERROR_SUCCESS) {
            format_result = FormatFloatArray(
                sample.state.up, 3U, up.data(), up.size()
            );
        }
        if (format_result == ERROR_SUCCESS) {
            format_result = FormatFloatArray(
                sample.state.view_matrix, 16U, view.data(), view.size()
            );
        }
        if (format_result == ERROR_SUCCESS) {
            format_result = FormatFloatArray(
                sample.state.projection_matrix,
                16U,
                projection.data(),
                projection.size()
            );
        }
        if (format_result != ERROR_SUCCESS) {
            return format_result;
        }
        result = StringCchPrintfExA(
            cursor,
            remaining,
            &cursor,
            &remaining,
            0U,
            "%s{\"sequence\":%llu,\"present_sequence\":%llu,\"counter\":%lld,"
            "\"position\":%s,\"forward\":%s,\"up\":%s,"
            "\"zoom\":%.9g,\"vertical_fov_degrees\":%.9g,"
            "\"view_matrix\":%s,\"projection_matrix\":%s,"
            "\"viewport\":[%d,%d,%d,%d]}",
            first_sample ? "" : ",",
            static_cast<unsigned long long>(sample.sequence),
            static_cast<unsigned long long>(sample.present_sequence),
            static_cast<long long>(sample.counter),
            position.data(),
            forward.data(),
            up.data(),
            static_cast<double>(sample.state.zoom),
            static_cast<double>(sample.state.vertical_fov_degrees),
            view.data(),
            projection.data(),
            sample.state.viewport[0],
            sample.state.viewport[1],
            sample.state.viewport[2],
            sample.state.viewport[3]
        );
        if (FAILED(result)) {
            return HResultToWin32(result);
        }
        first_sample = false;
    }
    result = StringCchCopyA(cursor, remaining, "]}");
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

DWORD PublishSnapshot(const PublisherSnapshot& snapshot) noexcept {
    std::array<char, kExecutablePathUtf8Capacity> executable_utf8{};
    std::array<char, kEscapedPathCapacity> executable_json{};
    std::array<char, kEscapedDriverStringCapacity> gl_version_json{};
    std::array<char, kEscapedDriverStringCapacity> glsl_version_json{};
    if (!Utf8Path(
            snapshot.executable_path,
            executable_utf8.data(),
            executable_utf8.size()
        ) || !JsonString(
            executable_utf8.data(),
            executable_json.data(),
            executable_json.size()
        ) || !JsonStringOrNull(
            snapshot.status.graphics_context.gl_version,
            gl_version_json.data(),
            gl_version_json.size()
        ) || !JsonStringOrNull(
            snapshot.status.graphics_context.glsl_version,
            glsl_version_json.data(),
            glsl_version_json.size()
        )) {
        return ERROR_INSUFFICIENT_BUFFER;
    }
    std::array<char, 1024U> entries_json{};
    std::array<char, 512U> active_json{};
    if (snapshot.status.configured) {
        HRESULT result = StringCchPrintfA(
            entries_json.data(),
            entries_json.size(),
            "[{\"library\":\"%s\",\"symbol\":\"%s\",\"iat_rva\":%lu,"
            "\"call_count\":%llu}]",
            snapshot.status.library_name,
            snapshot.status.symbol_name,
            static_cast<unsigned long>(snapshot.status.iat_rva),
            static_cast<unsigned long long>(snapshot.status.call_count)
        );
        if (FAILED(result)) {
            return HResultToWin32(result);
        }
        if (snapshot.status.call_count > 0U) {
            result = StringCchPrintfA(
                active_json.data(),
                active_json.size(),
                "{\"library\":\"%s\",\"symbol\":\"%s\",\"iat_rva\":%lu}",
                snapshot.status.library_name,
                snapshot.status.symbol_name,
                static_cast<unsigned long>(snapshot.status.iat_rva)
            );
        } else {
            result = StringCchCopyA(active_json.data(), active_json.size(), "null");
        }
        if (FAILED(result)) {
            return HResultToWin32(result);
        }
    } else {
        StringCchCopyA(entries_json.data(), entries_json.size(), "[]");
        StringCchCopyA(active_json.data(), active_json.size(), "null");
    }
    std::array<char, 1024U> context_json{};
    const GraphicsContextSnapshot& context = snapshot.status.graphics_context;
    HRESULT result = S_OK;
    if (context.observed) {
        result = StringCchPrintfA(
            context_json.data(),
            context_json.size(),
            "{\"context_observed\":true,\"gl_version\":%s,\"glsl_version\":%s,"
            "\"depth_bits\":%d,\"depth_texture_supported\":%s,"
            "\"framebuffer_object_supported\":%s,\"viewport\":[%d,%d,%d,%d]}",
            gl_version_json.data(),
            glsl_version_json.data(),
            context.depth_bits,
            context.depth_texture_supported ? "true" : "false",
            context.framebuffer_object_supported ? "true" : "false",
            context.viewport[0],
            context.viewport[1],
            context.viewport[2],
            context.viewport[3]
        );
    } else {
        result = StringCchCopyA(
            context_json.data(),
            context_json.size(),
            "{\"context_observed\":false,\"gl_version\":null,\"glsl_version\":null,"
            "\"depth_bits\":null,\"depth_texture_supported\":null,"
            "\"framebuffer_object_supported\":null,\"viewport\":null}"
        );
    }
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    std::array<char, kFrameTimingJsonCapacity> frame_timing_json{};
    const DWORD timing_result = FormatFrameTiming(
        snapshot,
        frame_timing_json.data(),
        frame_timing_json.size()
    );
    if (timing_result != ERROR_SUCCESS) {
        return timing_result;
    }
    std::array<char, kCameraStateJsonCapacity> camera_state_json{};
    const DWORD camera_result = FormatCameraState(
        snapshot,
        camera_state_json.data(),
        camera_state_json.size()
    );
    if (camera_result != ERROR_SUCCESS) {
        return camera_result;
    }
    const char* depth_edge_state = "armed";
    const char* depth_edge_reason = "awaiting-reviewed-client-pre-ui-boundary";
    if (snapshot.status.depth_edge_failed) {
        depth_edge_state = "failed";
        depth_edge_reason = snapshot.status.depth_edge_failure_reason;
    } else if (snapshot.status.depth_edge_composite_count > 0U) {
        depth_edge_state = "active";
        depth_edge_reason = "fixed-pixel-single-owner-inverse-depth-curvature";
    }
    std::array<char, kEscapedDepthEdgeReasonCapacity> depth_edge_reason_json{};
    if (!JsonString(
            depth_edge_reason,
            depth_edge_reason_json.data(),
            depth_edge_reason_json.size()
        )) {
        return ERROR_INSUFFICIENT_BUFFER;
    }
    std::array<char, 512U> depth_edge_json{};
    result = StringCchPrintfA(
        depth_edge_json.data(),
        depth_edge_json.size(),
        "{\"state\":\"%s\",\"reason\":%s,\"composite_count\":%llu,"
        "\"radius_pixels\":1.0,"
        "\"edge_metric\":\"single-owner-inverse-depth-curvature\","
        "\"sample_kernel\":\"cardinal-five-sample\","
        "\"composite_boundary\":\"reviewed-client-done3d\"}",
        depth_edge_state,
        depth_edge_reason_json.data(),
        static_cast<unsigned long long>(
            snapshot.status.depth_edge_composite_count
        )
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    const char* scene_color_state = "armed";
    const char* scene_color_reason = "awaiting-pre-ui-scene-boundary";
    if (snapshot.status.scene_color_failed) {
        scene_color_state = "fallback";
        scene_color_reason = snapshot.status.scene_color_failure_reason;
    } else if (snapshot.status.scene_color_capture_count > 0U) {
        scene_color_state = "active";
        scene_color_reason = "single-pre-ui-gpu-copy";
    }
    std::array<char, kEscapedDepthEdgeReasonCapacity> scene_color_reason_json{};
    if (!JsonString(
            scene_color_reason,
            scene_color_reason_json.data(),
            scene_color_reason_json.size()
        )) {
        return ERROR_INSUFFICIENT_BUFFER;
    }
    std::array<char, 512U> scene_color_json{};
    result = StringCchPrintfA(
        scene_color_json.data(),
        scene_color_json.size(),
        "{\"schema_version\":1,\"state\":\"%s\",\"reason\":%s,"
        "\"capture_count\":%llu,"
        "\"copy_boundary\":\"before-ui\",\"copy_frequency\":\"once-per-frame\","
        "\"transport\":\"gpu-to-gpu\",\"cpu_readback\":false}",
        scene_color_state,
        scene_color_reason_json.data(),
        static_cast<unsigned long long>(
            snapshot.status.scene_color_capture_count
        )
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    const char* scene_frame_state = snapshot.status.classified_frame_count > 0U
        ? "active"
        : "armed";
    const char* scene_frame_phase = "awaiting-world";
    if (snapshot.status.latest_scene_frame.phase == SceneFramePhase::world) {
        scene_frame_phase = "world";
    } else if (snapshot.status.latest_scene_frame.phase == SceneFramePhase::ui) {
        scene_frame_phase = "ui";
    }
    const auto& latest_layers = snapshot.status.latest_scene_frame.draw_counts;
    const auto& latest_reasons = snapshot.status.latest_scene_frame.reason_counts;
    const auto& total_layers = snapshot.status.classified_draw_counts;
    const auto& total_reasons = snapshot.status.classification_reason_counts;
    std::array<char, 6144U> scene_frame_json{};
    result = StringCchPrintfA(
        scene_frame_json.data(),
        scene_frame_json.size(),
        "{\"schema_version\":1,\"state\":\"%s\","
        "\"classified_frame_count\":%llu,"
        "\"latest\":{\"phase\":\"%s\",\"layers\":{"
        "\"unknown\":%llu,\"world_opaque\":%llu,"
        "\"world_alpha_tested\":%llu,\"world_translucent\":%llu,"
        "\"world_overlay\":%llu,\"ui_overlay\":%llu},\"reasons\":{"
        "\"projection_unavailable\":%llu,\"orthographic_projection\":%llu,"
        "\"planar_overlay_state\":%llu,\"depth_writing_opaque\":%llu,"
        "\"depth_writing_alpha_tested\":%llu,\"blended_perspective\":%llu,"
        "\"depthless_perspective\":%llu},\"boundary_count\":%llu,"
        "\"late_world_draw_count\":%llu,"
        "\"draw_count\":%llu,\"world_draw_count\":%llu,"
        "\"composite_candidate_count\":%llu,"
        "\"rejected_composite_candidate_count\":%llu,"
        "\"first_world_draw_ordinal\":%llu,"
        "\"first_composite_candidate_draw_ordinal\":%llu,"
        "\"accepted_boundary_draw_ordinal\":%llu,"
        "\"first_late_world_draw_ordinal\":%llu,"
        "\"last_world_draw_ordinal\":%llu,"
        "\"fixed_function_refresh_count\":%llu,"
        "\"fixed_function_state_invalidation_count\":%llu,"
        "\"feature_accent_draw_count\":%llu,"
        "\"feature_accent_skipped_blend_count\":%llu,"
        "\"feature_accent_skipped_source_state_count\":%llu,"
        "\"feature_accent_skipped_uv_segment_count\":%llu,"
        "\"main_scene_start_count\":%llu,\"main_scene_world_draw_count\":%llu,"
        "\"boundary_mapping_verified\":%s,\"main_scene_invalidated\":%s,"
        "\"composite_succeeded\":%s},\"totals\":{\"layers\":{"
        "\"unknown\":%llu,\"world_opaque\":%llu,"
        "\"world_alpha_tested\":%llu,\"world_translucent\":%llu,"
        "\"world_overlay\":%llu,\"ui_overlay\":%llu},\"reasons\":{"
        "\"projection_unavailable\":%llu,\"orthographic_projection\":%llu,"
        "\"planar_overlay_state\":%llu,\"depth_writing_opaque\":%llu,"
        "\"depth_writing_alpha_tested\":%llu,\"blended_perspective\":%llu,"
        "\"depthless_perspective\":%llu},\"boundary_count\":%llu,"
        "\"late_world_draw_count\":%llu,"
        "\"fixed_function_refresh_count\":%llu},\"policy\":{"
        "\"single_world_to_ui_boundary\":true,"
        "\"boundary_ownership\":\"reviewed-client-done3d\","
        "\"candidate_retry\":\"never-from-draw-state\","
        "\"planar_overlay\":\"excluded-without-sealing-scene\","
        "\"late_world_after_ui\":\"excluded-and-counted\","
        "\"fixed_function_state\":\"cached-with-transition-hooks\","
        "\"state_boundary_refreshes\":\"counted-invalidations\","
        "\"maximum_ordinary_frame_refreshes\":1}}",
        scene_frame_state,
        static_cast<unsigned long long>(snapshot.status.classified_frame_count),
        scene_frame_phase,
        static_cast<unsigned long long>(latest_layers[0]),
        static_cast<unsigned long long>(latest_layers[1]),
        static_cast<unsigned long long>(latest_layers[2]),
        static_cast<unsigned long long>(latest_layers[3]),
        static_cast<unsigned long long>(latest_layers[4]),
        static_cast<unsigned long long>(latest_layers[5]),
        static_cast<unsigned long long>(latest_reasons[0]),
        static_cast<unsigned long long>(latest_reasons[1]),
        static_cast<unsigned long long>(latest_reasons[2]),
        static_cast<unsigned long long>(latest_reasons[3]),
        static_cast<unsigned long long>(latest_reasons[4]),
        static_cast<unsigned long long>(latest_reasons[5]),
        static_cast<unsigned long long>(latest_reasons[6]),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.boundary_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.late_world_draw_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.draw_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.world_draw_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.composite_candidate_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.rejected_composite_candidate_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.first_world_draw_ordinal
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame
                .first_composite_candidate_draw_ordinal
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.accepted_boundary_draw_ordinal
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.first_late_world_draw_ordinal
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.last_world_draw_ordinal
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.fixed_function_refresh_count
        ),
        static_cast<unsigned long long>(
            snapshot.status.latest_scene_frame.fixed_function_state_invalidation_count
        ),
        static_cast<unsigned long long>(snapshot.status.latest_scene_frame.feature_accent_draw_count),
        static_cast<unsigned long long>(snapshot.status.latest_scene_frame.feature_accent_skipped_blend_count),
        static_cast<unsigned long long>(snapshot.status.latest_scene_frame.feature_accent_skipped_source_state_count),
        static_cast<unsigned long long>(snapshot.status.latest_scene_frame.feature_accent_skipped_uv_segment_count),
        static_cast<unsigned long long>(snapshot.status.latest_scene_frame.main_scene_start_count),
        static_cast<unsigned long long>(snapshot.status.latest_scene_frame.main_scene_world_draw_count),
        snapshot.status.latest_scene_frame.boundary_mapping_verified ? "true" : "false",
        snapshot.status.latest_scene_frame.main_scene_invalidated ? "true" : "false",
        snapshot.status.latest_scene_frame.composite_succeeded ? "true" : "false",
        static_cast<unsigned long long>(total_layers[0]),
        static_cast<unsigned long long>(total_layers[1]),
        static_cast<unsigned long long>(total_layers[2]),
        static_cast<unsigned long long>(total_layers[3]),
        static_cast<unsigned long long>(total_layers[4]),
        static_cast<unsigned long long>(total_layers[5]),
        static_cast<unsigned long long>(total_reasons[0]),
        static_cast<unsigned long long>(total_reasons[1]),
        static_cast<unsigned long long>(total_reasons[2]),
        static_cast<unsigned long long>(total_reasons[3]),
        static_cast<unsigned long long>(total_reasons[4]),
        static_cast<unsigned long long>(total_reasons[5]),
        static_cast<unsigned long long>(total_reasons[6]),
        static_cast<unsigned long long>(snapshot.status.scene_boundary_count),
        static_cast<unsigned long long>(snapshot.status.late_world_draw_count),
        static_cast<unsigned long long>(
            snapshot.status.fixed_function_refresh_count
        )
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    const GraphicsControlStatus control = GetGraphicsControlStatus();
    std::array<char, 1536U> control_json{};
    if (control.available) {
        std::array<char, kControlNameUtf8Capacity> control_name_utf8{};
        std::array<char, kEscapedControlNameCapacity> control_name_json{};
        if (!Utf8Path(
                control.mapping_name,
                control_name_utf8.data(),
                control_name_utf8.size()
            ) || !JsonString(
                control_name_utf8.data(),
                control_name_json.data(),
                control_name_json.size()
            )) {
            return ERROR_INSUFFICIENT_BUFFER;
        }
        const GraphicsParametersSnapshot parameter_snapshot =
            SnapshotGraphicsParameters();
        const GraphicsParameters& parameters = parameter_snapshot.parameters;
        result = StringCchPrintfA(
            control_json.data(),
            control_json.size(),
            "{\"available\":true,\"schema_version\":%lu,\"mapping_name\":%s,"
            "\"desired_sequence\":%ld,\"applied_sequence\":%ld,"
            "\"rejected_sequence\":%ld,\"last_error\":%lu,"
            "\"parameters_revision\":%lu,\"depth_contours_enabled\":%s,"
            "\"depth_contour_mode\":\"%s\","
            "\"depth_contour_debug_mode\":\"%s\","
            "\"depth_edge_threshold\":%.9f,"
            "\"sustained_edge_threshold\":%.9f}",
            static_cast<unsigned long>(kGraphicsControlSchemaVersion),
            control_name_json.data(),
            static_cast<long>(control.desired_sequence),
            static_cast<long>(control.applied_sequence),
            static_cast<long>(control.rejected_sequence),
            static_cast<unsigned long>(control.last_error),
            static_cast<unsigned long>(parameter_snapshot.revision),
            (parameters.flags & kGraphicsControlDepthContours) != 0U
                ? "true"
                : "false",
            DepthContourModeName(parameters.depth_contour_mode),
            DepthContourDebugModeName(parameters.depth_contour_debug_mode),
            static_cast<double>(parameters.depth_edge_threshold),
            static_cast<double>(parameters.sustained_edge_threshold)
        );
    } else {
        result = StringCchPrintfA(
            control_json.data(),
            control_json.size(),
            "{\"available\":false,\"schema_version\":%lu,"
            "\"mapping_name\":null,\"desired_sequence\":null,"
            "\"applied_sequence\":null,\"rejected_sequence\":null,"
            "\"last_error\":null,\"parameters_revision\":null,"
            "\"depth_contours_enabled\":null,"
            "\"depth_contour_mode\":null,"
            "\"depth_contour_debug_mode\":null,"
            "\"depth_edge_threshold\":null,"
            "\"sustained_edge_threshold\":null}",
            static_cast<unsigned long>(kGraphicsControlSchemaVersion)
        );
    }
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    std::array<char, kJsonCapacity> json{};
    result = StringCchPrintfA(
        json.data(),
        json.size(),
        "{\"schema_version\":2,\"producer_id\":\"%s\","
        "\"extension_version\":\"%s\",\"process_identity\":{"
        "\"process_id\":%lu,\"process_creation_filetime_utc\":%llu,"
        "\"executable_path\":%s},\"executable_sha256\":\"%s\","
        "\"runtime_profile\":\"%s\","
        "\"present_entries\":%s,\"active_present_entry\":%s,"
        "\"graphics_context\":%s,\"frame_timing\":%s,"
        "\"camera_state\":%s,\"depth_edge_pass\":%s,"
        "\"scene_color_capture\":%s,\"draw_classification\":%s,"
        "\"live_controls\":%s}\n",
        kProducerId,
        kExtensionVersion,
        static_cast<unsigned long>(snapshot.process_id),
        static_cast<unsigned long long>(snapshot.process_creation_filetime_utc),
        executable_json.data(),
        snapshot.executable_sha256,
        snapshot.status.runtime_profile,
        entries_json.data(),
        active_json.data(),
        context_json.data(),
        frame_timing_json.data(),
        camera_state_json.data(),
        depth_edge_json.data(),
        scene_color_json.data(),
        scene_frame_json.data(),
        control_json.data()
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    wchar_t temporary_path[kPathCapacity]{};
    result = StringCchPrintfW(
        temporary_path,
        kPathCapacity,
        L"%s.%lu.%llu.tmp",
        snapshot.final_path,
        static_cast<unsigned long>(GetCurrentThreadId()),
        static_cast<unsigned long long>(GetTickCount64())
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    const HANDLE file = CreateFileW(
        temporary_path,
        GENERIC_WRITE,
        0U,
        nullptr,
        CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL,
        nullptr
    );
    if (file == INVALID_HANDLE_VALUE) {
        return GetLastError();
    }
    DWORD write_result = WriteAll(
        file,
        json.data(),
        static_cast<DWORD>(std::strlen(json.data()))
    );
    if (write_result == ERROR_SUCCESS && FlushFileBuffers(file) == FALSE) {
        write_result = GetLastError();
    }
    if (CloseHandle(file) == FALSE && write_result == ERROR_SUCCESS) {
        write_result = GetLastError();
    }
    if (write_result != ERROR_SUCCESS) {
        DeleteFileW(temporary_path);
        return write_result;
    }
    if (MoveFileExW(
            temporary_path,
            snapshot.final_path,
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
        ) == FALSE) {
        write_result = GetLastError();
        DeleteFileW(temporary_path);
        return write_result;
    }
    return ERROR_SUCCESS;
}

DWORD PublishWithRetry(const PublisherSnapshot& snapshot) noexcept {
    DWORD result = ERROR_GEN_FAILURE;
    for (DWORD attempt = 0U; attempt < 10U; ++attempt) {
        result = PublishSnapshot(snapshot);
        if (result == ERROR_SUCCESS) {
            return ERROR_SUCCESS;
        }
        if (result != ERROR_SHARING_VIOLATION && result != ERROR_ACCESS_DENIED) {
            return result;
        }
        Sleep(50U);
    }
    return result;
}

DWORD WINAPI PublisherThread(LPVOID) noexcept {
    const HANDLE events[2U]{g_stop_event, g_wake_event};
    bool initial_publish_pending = true;
    for (;;) {
        const DWORD wait = WaitForMultipleObjects(2U, events, FALSE, INFINITE);
        if (wait == WAIT_OBJECT_0) {
            const DWORD publish_result = PublishWithRetry(SnapshotState());
            if (initial_publish_pending) {
                InterlockedExchange(
                    &g_initial_publish_result,
                    static_cast<LONG>(publish_result)
                );
                SetEvent(g_ready_event);
            }
            return ERROR_SUCCESS;
        }
        if (wait == WAIT_OBJECT_0 + 1U) {
            const DWORD publish_result = PublishWithRetry(SnapshotState());
            if (initial_publish_pending) {
                initial_publish_pending = false;
                InterlockedExchange(
                    &g_initial_publish_result,
                    static_cast<LONG>(publish_result)
                );
                SetEvent(g_ready_event);
            }
            continue;
        }
        return GetLastError();
    }
}

}  // namespace

bool HasGraphicsExtensionToken(
    const char* const extensions,
    const char* const token
) noexcept {
    if (extensions == nullptr || token == nullptr || token[0] == '\0'
        || std::strchr(token, ' ') != nullptr) {
        return false;
    }
    const std::size_t token_length = std::strlen(token);
    const char* cursor = extensions;
    while (*cursor != '\0') {
        while (*cursor == ' ') {
            ++cursor;
        }
        const char* const start = cursor;
        while (*cursor != '\0' && *cursor != ' ') {
            ++cursor;
        }
        if (static_cast<std::size_t>(cursor - start) == token_length
            && std::memcmp(start, token, token_length) == 0) {
            return true;
        }
    }
    return false;
}

bool IsGraphicsVersionAtLeast(
    const char* const version,
    const unsigned int required_major,
    const unsigned int required_minor
) noexcept {
    if (version == nullptr || !std::isdigit(static_cast<unsigned char>(version[0]))) {
        return false;
    }
    unsigned int major = 0U;
    unsigned int minor = 0U;
    const char* cursor = version;
    while (std::isdigit(static_cast<unsigned char>(*cursor))) {
        const unsigned int digit = static_cast<unsigned int>(*cursor - '0');
        if (major > (UINT_MAX - digit) / 10U) {
            return false;
        }
        major = major * 10U + digit;
        ++cursor;
    }
    if (*cursor++ != '.' || !std::isdigit(static_cast<unsigned char>(*cursor))) {
        return false;
    }
    while (std::isdigit(static_cast<unsigned char>(*cursor))) {
        const unsigned int digit = static_cast<unsigned int>(*cursor - '0');
        if (minor > (UINT_MAX - digit) / 10U) {
            return false;
        }
        minor = minor * 10U + digit;
        ++cursor;
    }
    return major > required_major
        || (major == required_major && minor >= required_minor);
}

bool BuildGraphicsCameraState(
    const float* const view_matrix,
    const std::size_t view_matrix_count,
    const float* const projection_matrix,
    const std::size_t projection_matrix_count,
    const int* const viewport,
    const std::size_t viewport_count,
    GraphicsCameraState* const state
) noexcept {
    if (view_matrix == nullptr || view_matrix_count != 16U
        || projection_matrix == nullptr || projection_matrix_count != 16U
        || viewport == nullptr || viewport_count != 4U || state == nullptr
        || viewport[2] <= 0 || viewport[3] <= 0) {
        return false;
    }
    for (std::size_t index = 0U; index < 16U; ++index) {
        if (!std::isfinite(view_matrix[index])
            || !std::isfinite(projection_matrix[index])
            || std::fabs(view_matrix[index]) > 1.0e9F
            || std::fabs(projection_matrix[index]) > 1.0e9F) {
            return false;
        }
    }
    if (std::fabs(view_matrix[3]) > 0.001F
        || std::fabs(view_matrix[7]) > 0.001F
        || std::fabs(view_matrix[11]) > 0.001F
        || std::fabs(view_matrix[15] - 1.0F) > 0.001F
        || std::fabs(projection_matrix[15]) > 0.001F
        || std::fabs(projection_matrix[11]) <= 0.25F) {
        return false;
    }
    const double right[3U]{
        view_matrix[0], view_matrix[4], view_matrix[8]
    };
    const double camera_up[3U]{
        view_matrix[1], view_matrix[5], view_matrix[9]
    };
    const double backward[3U]{
        view_matrix[2], view_matrix[6], view_matrix[10]
    };
    const auto length = [](const double* const vector) noexcept {
        return std::sqrt(
            vector[0] * vector[0]
            + vector[1] * vector[1]
            + vector[2] * vector[2]
        );
    };
    const auto dot = [](const double* const left, const double* const right_value) noexcept {
        return left[0] * right_value[0]
            + left[1] * right_value[1]
            + left[2] * right_value[2];
    };
    const double right_length = length(right);
    const double up_length = length(camera_up);
    const double backward_length = length(backward);
    if (!std::isfinite(right_length) || !std::isfinite(up_length)
        || !std::isfinite(backward_length)
        || std::fabs(right_length - 1.0) > 0.001
        || std::fabs(up_length - 1.0) > 0.001
        || std::fabs(backward_length - 1.0) > 0.001
        || std::fabs(dot(right, camera_up)) > 0.001
        || std::fabs(dot(right, backward)) > 0.001
        || std::fabs(dot(camera_up, backward)) > 0.001) {
        return false;
    }
    const double cross_up_backward[3U]{
        camera_up[1] * backward[2] - camera_up[2] * backward[1],
        camera_up[2] * backward[0] - camera_up[0] * backward[2],
        camera_up[0] * backward[1] - camera_up[1] * backward[0],
    };
    if (std::fabs(dot(right, cross_up_backward) - 1.0) > 0.001) {
        return false;
    }
    const double vertical_scale = std::fabs(
        static_cast<double>(projection_matrix[5])
    );
    if (!std::isfinite(vertical_scale) || vertical_scale <= 0.000001
        || vertical_scale > 1.0e6) {
        return false;
    }
    constexpr double kRadiansToDegrees = 57.2957795130823208768;
    const double vertical_fov = 2.0 * std::atan(1.0 / vertical_scale)
        * kRadiansToDegrees;
    if (!std::isfinite(vertical_fov) || vertical_fov <= 0.0
        || vertical_fov >= 180.0) {
        return false;
    }
    GraphicsCameraState candidate{};
    candidate.position[0] = static_cast<float>(-(
        right[0] * view_matrix[12]
        + camera_up[0] * view_matrix[13]
        + backward[0] * view_matrix[14]
    ));
    candidate.position[1] = static_cast<float>(-(
        right[1] * view_matrix[12]
        + camera_up[1] * view_matrix[13]
        + backward[1] * view_matrix[14]
    ));
    candidate.position[2] = static_cast<float>(-(
        right[2] * view_matrix[12]
        + camera_up[2] * view_matrix[13]
        + backward[2] * view_matrix[14]
    ));
    for (std::size_t axis = 0U; axis < 3U; ++axis) {
        if (!std::isfinite(candidate.position[axis])
            || std::fabs(candidate.position[axis]) > 1.0e9F) {
            return false;
        }
        candidate.forward[axis] = static_cast<float>(-backward[axis]);
        candidate.up[axis] = static_cast<float>(camera_up[axis]);
    }
    candidate.zoom = static_cast<float>(vertical_scale);
    candidate.vertical_fov_degrees = static_cast<float>(vertical_fov);
    for (std::size_t index = 0U; index < 16U; ++index) {
        candidate.view_matrix[index] = view_matrix[index];
        candidate.projection_matrix[index] = projection_matrix[index];
    }
    for (std::size_t index = 0U; index < 4U; ++index) {
        candidate.viewport[index] = viewport[index];
    }
    *state = candidate;
    return true;
}

bool NeedsGraphicsCameraStateObservation() noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0) {
        return false;
    }
    AcquireSRWLockShared(&g_state_lock);
    const bool needed = g_status.configured
        && g_status.call_count != UINT64_MAX
        && (!g_status.pending_camera_valid
            || g_status.pending_camera_present_sequence != g_status.call_count + 1U
            || !g_status.pending_camera_ambiguous);
    ReleaseSRWLockShared(&g_state_lock);
    return needed;
}

void ObserveGraphicsCameraState(
    const float* const view_matrix,
    const std::size_t view_matrix_count,
    const float* const projection_matrix,
    const std::size_t projection_matrix_count,
    const int* const viewport,
    const std::size_t viewport_count,
    const int model_view_stack_depth
) noexcept {
    if (model_view_stack_depth != 1 || !NeedsGraphicsCameraStateObservation()) {
        return;
    }
    GraphicsCameraState camera{};
    if (!BuildGraphicsCameraState(
            view_matrix,
            view_matrix_count,
            projection_matrix,
            projection_matrix_count,
            viewport,
            viewport_count,
            &camera
        )) {
        return;
    }
    LARGE_INTEGER counter{};
    const bool counter_observed = QueryPerformanceCounter(&counter) != FALSE
        && counter.QuadPart > 0;
    AcquireSRWLockExclusive(&g_state_lock);
    if (g_status.configured && g_status.call_count != UINT64_MAX) {
        const std::uint64_t present_sequence = g_status.call_count + 1U;
        if (!g_status.pending_camera_valid
            || g_status.pending_camera_present_sequence != present_sequence) {
            if (counter_observed) {
                g_status.pending_camera_valid = true;
                g_status.pending_camera_ambiguous = false;
                g_status.pending_camera_present_sequence = present_sequence;
                g_status.pending_camera = {0U, present_sequence, counter.QuadPart, camera};
            } else {
                ++g_status.camera_producer_drop_count;
            }
        } else if (!g_status.pending_camera_ambiguous
                   && (std::memcmp(
                           g_status.pending_camera.state.view_matrix,
                           camera.view_matrix,
                           sizeof(camera.view_matrix)
                       ) != 0
                       || std::memcmp(
                           g_status.pending_camera.state.projection_matrix,
                           camera.projection_matrix,
                           sizeof(camera.projection_matrix)
                       ) != 0
                       || std::memcmp(
                           g_status.pending_camera.state.viewport,
                           camera.viewport,
                           sizeof(camera.viewport)
                       ) != 0)) {
            g_status.pending_camera_ambiguous = true;
        }
    }
    ReleaseSRWLockExclusive(&g_state_lock);
}

DWORD StartGraphicsStatusPublication() noexcept {
    if (InterlockedCompareExchange(&g_started, 1, 0) != 0) {
        return ERROR_ALREADY_INITIALIZED;
    }
    wchar_t executable_path[kPathCapacity]{};
    const DWORD executable_length = GetModuleFileNameW(
        nullptr,
        executable_path,
        static_cast<DWORD>(std::size(executable_path))
    );
    DWORD result = ERROR_SUCCESS;
    if (executable_length == 0U) {
        result = GetLastError();
    } else if (executable_length >= std::size(executable_path)) {
        result = ERROR_INSUFFICIENT_BUFFER;
    }
    FILETIME creation_time{};
    FILETIME exit_time{};
    FILETIME kernel_time{};
    FILETIME user_time{};
    if (result == ERROR_SUCCESS && GetProcessTimes(
            GetCurrentProcess(),
            &creation_time,
            &exit_time,
            &kernel_time,
            &user_time
        ) == FALSE) {
        result = GetLastError();
    }
    char executable_sha256[65U]{};
    if (result == ERROR_SUCCESS) {
        result = Sha256File(
            executable_path,
            executable_sha256,
            std::size(executable_sha256)
        );
    }
    PWSTR local_app_data = nullptr;
    if (result == ERROR_SUCCESS) {
        const HRESULT known_folder_result = SHGetKnownFolderPath(
            FOLDERID_LocalAppData,
            KF_FLAG_CREATE,
            nullptr,
            &local_app_data
        );
        if (FAILED(known_folder_result)) {
            result = HResultToWin32(known_folder_result);
        }
    }
    wchar_t product_directory[kPathCapacity]{};
    wchar_t extension_directory[kPathCapacity]{};
    if (result == ERROR_SUCCESS) {
        result = CombinePath(
            product_directory,
            kPathCapacity,
            local_app_data,
            kProductDirectory
        );
    }
    if (local_app_data != nullptr) {
        CoTaskMemFree(local_app_data);
    }
    if (result == ERROR_SUCCESS) {
        result = RequireOrdinaryDirectory(product_directory);
    }
    if (result == ERROR_SUCCESS) {
        result = CombinePath(
            extension_directory,
            kPathCapacity,
            product_directory,
            kExtensionDirectory
        );
    }
    if (result == ERROR_SUCCESS) {
        result = RequireOrdinaryDirectory(extension_directory);
    }
    LARGE_INTEGER performance_counter_frequency{};
    if (result == ERROR_SUCCESS && (
            QueryPerformanceFrequency(&performance_counter_frequency) == FALSE
            || performance_counter_frequency.QuadPart <= 0
        )) {
        result = GetLastError();
        if (result == ERROR_SUCCESS) {
            result = ERROR_GEN_FAILURE;
        }
    }
    wchar_t final_path[kPathCapacity]{};
    const DWORD process_id = GetCurrentProcessId();
    const std::uint64_t creation_value = FileTimeValue(creation_time);
    if (result == ERROR_SUCCESS) {
        const HRESULT format_result = StringCchPrintfW(
            final_path,
            kPathCapacity,
            L"%s\\graphics-status-%lu-%llu.json",
            extension_directory,
            static_cast<unsigned long>(process_id),
            static_cast<unsigned long long>(creation_value)
        );
        if (FAILED(format_result)) {
            result = HResultToWin32(format_result);
        }
    }
    HANDLE stop_event = nullptr;
    HANDLE wake_event = nullptr;
    HANDLE ready_event = nullptr;
    if (result == ERROR_SUCCESS) {
        stop_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (stop_event == nullptr) {
            result = GetLastError();
        }
    }
    if (result == ERROR_SUCCESS) {
        wake_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        if (wake_event == nullptr) {
            result = GetLastError();
        }
    }
    if (result == ERROR_SUCCESS) {
        ready_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (ready_event == nullptr) {
            result = GetLastError();
        }
    }
    if (result == ERROR_SUCCESS) {
        AcquireSRWLockExclusive(&g_state_lock);
        g_process_id = process_id;
        g_process_creation_filetime_utc = creation_value;
        StringCchCopyW(g_executable_path, kPathCapacity, executable_path);
        StringCchCopyA(
            g_executable_sha256,
            std::size(g_executable_sha256),
            executable_sha256
        );
        StringCchCopyW(g_graphics_status_path, kPathCapacity, final_path);
        g_status = {};
        g_status.performance_counter_frequency = performance_counter_frequency.QuadPart;
        g_stop_event = stop_event;
        g_wake_event = wake_event;
        g_ready_event = ready_event;
        InterlockedExchange(&g_initial_publish_result, ERROR_IO_PENDING);
        ReleaseSRWLockExclusive(&g_state_lock);
        g_worker_thread = CreateThread(nullptr, 0U, PublisherThread, nullptr, 0U, nullptr);
        if (g_worker_thread == nullptr) {
            result = GetLastError();
        }
    }
    if (result == ERROR_SUCCESS) {
        SetEvent(g_wake_event);
        const DWORD ready = WaitForSingleObject(
            g_ready_event,
            kWorkerStopTimeoutMilliseconds
        );
        if (ready == WAIT_OBJECT_0) {
            result = static_cast<DWORD>(InterlockedCompareExchange(
                &g_initial_publish_result,
                0,
                0
            ));
        } else if (ready == WAIT_TIMEOUT) {
            result = ERROR_TIMEOUT;
        } else {
            result = GetLastError();
        }
        if (result == ERROR_SUCCESS) {
            return ERROR_SUCCESS;
        }
    }
    if (g_worker_thread != nullptr) {
        SetEvent(g_stop_event);
        WaitForSingleObject(g_worker_thread, kWorkerStopTimeoutMilliseconds);
        CloseHandle(g_worker_thread);
    }
    if (wake_event != nullptr) {
        CloseHandle(wake_event);
    }
    if (ready_event != nullptr) {
        CloseHandle(ready_event);
    }
    if (stop_event != nullptr) {
        CloseHandle(stop_event);
    }
    g_worker_thread = nullptr;
    g_wake_event = nullptr;
    g_ready_event = nullptr;
    g_stop_event = nullptr;
    InterlockedExchange(&g_started, 0);
    return result;
}

DWORD ConfigureGraphicsPresentEntry(
    const char* const library_name,
    const char* const symbol_name,
    const std::uint32_t iat_rva,
    const char* const runtime_profile
) noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0
        || library_name == nullptr || symbol_name == nullptr
        || runtime_profile == nullptr || library_name[0] == '\0'
        || symbol_name[0] == '\0' || runtime_profile[0] == '\0') {
        return ERROR_INVALID_STATE;
    }
    AcquireSRWLockExclusive(&g_state_lock);
    HRESULT result = StringCchCopyA(
        g_status.runtime_profile,
        std::size(g_status.runtime_profile),
        runtime_profile
    );
    if (SUCCEEDED(result)) {
        result = StringCchCopyA(
            g_status.library_name,
            std::size(g_status.library_name),
            library_name
        );
    }
    if (SUCCEEDED(result)) {
        result = StringCchCopyA(
            g_status.symbol_name,
            std::size(g_status.symbol_name),
            symbol_name
        );
    }
    if (SUCCEEDED(result)) {
        g_status.configured = true;
        g_status.iat_rva = iat_rva;
    }
    ReleaseSRWLockExclusive(&g_state_lock);
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    SetEvent(g_wake_event);
    return ERROR_SUCCESS;
}

bool GraphicsExecutableSha256Matches(const char* const sha256) noexcept {
    if (sha256 == nullptr) { return false; }
    AcquireSRWLockShared(&g_state_lock);
    const bool matches = g_executable_sha256[0] != '\0'
        && std::strcmp(g_executable_sha256, sha256) == 0;
    ReleaseSRWLockShared(&g_state_lock);
    return matches;
}

void ObserveGraphicsPresent() noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0) {
        return;
    }
    LARGE_INTEGER present_counter{};
    const bool timing_observed = QueryPerformanceCounter(&present_counter) != FALSE
        && present_counter.QuadPart > 0;
    GraphicsContextSnapshot context{};
    const HMODULE opengl = GetModuleHandleW(L"OPENGL32.dll");
    if (opengl != nullptr) {
        const auto get_current_context = reinterpret_cast<WglGetCurrentContext>(
            GetProcAddress(opengl, "wglGetCurrentContext")
        );
        if (get_current_context != nullptr) {
            const HGLRC current = get_current_context();
            const std::uintptr_t current_value = reinterpret_cast<std::uintptr_t>(current);
            AcquireSRWLockShared(&g_state_lock);
            const bool needs_context = current != nullptr
                && current_value != g_status.graphics_context.context;
            ReleaseSRWLockShared(&g_state_lock);
            if (needs_context) {
                context = QueryGraphicsContext();
            }
        }
    }
    bool publish = false;
    AcquireSRWLockExclusive(&g_state_lock);
    if (g_status.configured) {
        ++g_status.call_count;
        if (g_status.pending_camera_valid) {
            if (g_status.pending_camera_present_sequence == g_status.call_count
                && g_status.camera_sample_sequence != UINT64_MAX
                && !g_status.pending_camera_ambiguous) {
                ++g_status.camera_sample_sequence;
                CameraStateSample sample = g_status.pending_camera;
                sample.sequence = g_status.camera_sample_sequence;
                sample.present_sequence = g_status.call_count;
                const std::size_t camera_index = static_cast<std::size_t>(
                    (sample.sequence - 1U) % kCameraStateSampleCapacity
                );
                g_status.camera_state_samples[camera_index] = sample;
            } else {
                ++g_status.camera_producer_drop_count;
            }
            g_status.pending_camera_valid = false;
            g_status.pending_camera_ambiguous = false;
            g_status.pending_camera_present_sequence = 0U;
            g_status.pending_camera = {};
        }
        if (timing_observed) {
            const std::size_t timing_index = static_cast<std::size_t>(
                (g_status.call_count - 1U) % kFrameTimingSampleCapacity
            );
            g_status.frame_timing_samples[timing_index] = {
                g_status.call_count,
                present_counter.QuadPart,
            };
        } else {
            ++g_status.timing_query_failure_count;
        }
        if (context.observed) {
            g_status.graphics_context = context;
        }
        const ULONGLONG tick = GetTickCount64();
        publish = g_status.call_count == 1U
            || tick - g_status.last_publish_signal_tick >= kPublishIntervalMilliseconds;
        if (publish) {
            g_status.last_publish_signal_tick = tick;
        }
    }
    ReleaseSRWLockExclusive(&g_state_lock);
    if (publish) {
        SetEvent(g_wake_event);
    }
}

void ReportDepthEdgePassComposite() noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0) {
        return;
    }
    bool publish = false;
    AcquireSRWLockExclusive(&g_state_lock);
    ++g_status.depth_edge_composite_count;
    g_status.depth_edge_failed = false;
    g_status.depth_edge_failure_reason[0] = '\0';
    publish = g_status.depth_edge_composite_count == 1U;
    ReleaseSRWLockExclusive(&g_state_lock);
    if (publish) {
        SetEvent(g_wake_event);
    }
}

void ReportDepthEdgePassFailure(const char* const reason) noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0
        || reason == nullptr || reason[0] == '\0') {
        return;
    }
    bool publish = false;
    AcquireSRWLockExclusive(&g_state_lock);
    publish = !g_status.depth_edge_failed
        || std::strcmp(g_status.depth_edge_failure_reason, reason) != 0;
    g_status.depth_edge_failed = true;
    StringCchCopyA(
        g_status.depth_edge_failure_reason,
        std::size(g_status.depth_edge_failure_reason),
        reason
    );
    ReleaseSRWLockExclusive(&g_state_lock);
    if (publish) {
        SetEvent(g_wake_event);
    }
}

void ReportSceneColorCapture() noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0) {
        return;
    }
    bool publish = false;
    AcquireSRWLockExclusive(&g_state_lock);
    ++g_status.scene_color_capture_count;
    g_status.scene_color_failed = false;
    g_status.scene_color_failure_reason[0] = '\0';
    publish = g_status.scene_color_capture_count == 1U;
    ReleaseSRWLockExclusive(&g_state_lock);
    if (publish) {
        SetEvent(g_wake_event);
    }
}

void ReportSceneColorCaptureFailure(const char* const reason) noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0
        || reason == nullptr || reason[0] == '\0') {
        return;
    }
    bool publish = false;
    AcquireSRWLockExclusive(&g_state_lock);
    publish = !g_status.scene_color_failed
        || std::strcmp(g_status.scene_color_failure_reason, reason) != 0;
    g_status.scene_color_failed = true;
    StringCchCopyA(
        g_status.scene_color_failure_reason,
        std::size(g_status.scene_color_failure_reason),
        reason
    );
    ReleaseSRWLockExclusive(&g_state_lock);
    if (publish) {
        SetEvent(g_wake_event);
    }
}

void ReportSceneFrameClassification(const SceneFrameState& frame) noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0) {
        return;
    }
    bool publish = false;
    AcquireSRWLockExclusive(&g_state_lock);
    publish = g_status.classified_frame_count == 0U
        || frame.late_world_draw_count > 0U
        || (frame.fixed_function_refresh_count > 1U
            && frame.fixed_function_refresh_count - 1U
                > frame.fixed_function_state_invalidation_count);
    SaturatingAdd(&g_status.classified_frame_count, 1U);
    g_status.latest_scene_frame = frame;
    for (std::size_t index = 0U; index < frame.draw_counts.size(); ++index) {
        SaturatingAdd(
            &g_status.classified_draw_counts[index],
            frame.draw_counts[index]
        );
    }
    for (std::size_t index = 0U; index < frame.reason_counts.size(); ++index) {
        SaturatingAdd(
            &g_status.classification_reason_counts[index],
            frame.reason_counts[index]
        );
    }
    SaturatingAdd(&g_status.scene_boundary_count, frame.boundary_count);
    SaturatingAdd(
        &g_status.late_world_draw_count,
        frame.late_world_draw_count
    );
    SaturatingAdd(
        &g_status.fixed_function_refresh_count,
        frame.fixed_function_refresh_count
    );
    ReleaseSRWLockExclusive(&g_state_lock);
    if (publish) {
        SetEvent(g_wake_event);
    }
}

void StopGraphicsStatusPublication() noexcept {
    if (InterlockedExchange(&g_started, 0) == 0) {
        return;
    }
    const HANDLE thread = g_worker_thread;
    const HANDLE stop_event = g_stop_event;
    const HANDLE wake_event = g_wake_event;
    const HANDLE ready_event = g_ready_event;
    if (stop_event != nullptr) {
        SetEvent(stop_event);
    }
    if (thread != nullptr) {
        WaitForSingleObject(thread, kWorkerStopTimeoutMilliseconds);
        CloseHandle(thread);
    }
    if (wake_event != nullptr) {
        CloseHandle(wake_event);
    }
    if (ready_event != nullptr) {
        CloseHandle(ready_event);
    }
    if (stop_event != nullptr) {
        CloseHandle(stop_event);
    }
    AcquireSRWLockExclusive(&g_state_lock);
    g_worker_thread = nullptr;
    g_wake_event = nullptr;
    g_ready_event = nullptr;
    g_stop_event = nullptr;
    g_status = {};
    ReleaseSRWLockExclusive(&g_state_lock);
}

DWORD GetGraphicsStatusPath(
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (destination == nullptr || destination_capacity == 0U) {
        return ERROR_INVALID_PARAMETER;
    }
    AcquireSRWLockShared(&g_state_lock);
    const HRESULT result = StringCchCopyW(
        destination,
        destination_capacity,
        g_graphics_status_path
    );
    ReleaseSRWLockShared(&g_state_lock);
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

}  // namespace wonderbane::extension
