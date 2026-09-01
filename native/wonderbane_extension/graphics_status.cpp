#include "graphics_status.h"

#include "extension_api.h"

#include <KnownFolders.h>
#include <ShlObj.h>
#include <bcrypt.h>
#include <strsafe.h>

#include <array>
#include <cctype>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {

constexpr wchar_t kProductDirectory[] = L"ShadowbaneLab";
constexpr wchar_t kExtensionDirectory[] = L"client-extension";
constexpr char kProducerId[] = "wonderbane-extension.graphics";
constexpr char kExtensionVersion[] = "1.5.8";
constexpr std::size_t kPathCapacity = WONDERBANE_EXTENSION_HEARTBEAT_PATH_CAPACITY;
constexpr std::size_t kExecutablePathUtf8Capacity = kPathCapacity * 4U;
constexpr std::size_t kEscapedPathCapacity = kExecutablePathUtf8Capacity * 2U + 3U;
constexpr std::size_t kDriverStringCapacity = 256U;
constexpr std::size_t kEscapedDriverStringCapacity = kDriverStringCapacity * 2U + 3U;
constexpr std::size_t kDepthEdgeReasonCapacity = 128U;
constexpr std::size_t kEscapedDepthEdgeReasonCapacity =
    kDepthEdgeReasonCapacity * 2U + 3U;
constexpr std::size_t kJsonCapacity = 24U * 1024U;
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

struct GraphicsStatusState {
    bool configured = false;
    char library_name[64U]{};
    char symbol_name[128U]{};
    std::uint32_t iat_rva = 0U;
    std::uint64_t call_count = 0U;
    ULONGLONG last_publish_signal_tick = 0U;
    GraphicsContextSnapshot graphics_context{};
    std::uint64_t depth_edge_composite_count = 0U;
    bool depth_edge_failed = false;
    char depth_edge_failure_reason[kDepthEdgeReasonCapacity]{};
};

struct PublisherSnapshot {
    DWORD process_id = 0U;
    std::uint64_t process_creation_filetime_utc = 0U;
    wchar_t executable_path[kPathCapacity]{};
    char executable_sha256[65U]{};
    wchar_t final_path[kPathCapacity]{};
    GraphicsStatusState status{};
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
    return snapshot;
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
    const char* depth_edge_state = "armed";
    const char* depth_edge_reason = "awaiting-perspective-to-overlay-boundary";
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
        "\"composite_boundary\":\"perspective-to-overlay\"}",
        depth_edge_state,
        depth_edge_reason_json.data(),
        static_cast<unsigned long long>(
            snapshot.status.depth_edge_composite_count
        )
    );
    if (FAILED(result)) {
        return HResultToWin32(result);
    }
    std::array<char, kJsonCapacity> json{};
    result = StringCchPrintfA(
        json.data(),
        json.size(),
        "{\"schema_version\":1,\"producer_id\":\"%s\","
        "\"extension_version\":\"%s\",\"process_identity\":{"
        "\"process_id\":%lu,\"process_creation_filetime_utc\":%llu,"
        "\"executable_path\":%s},\"executable_sha256\":\"%s\","
        "\"present_entries\":%s,\"active_present_entry\":%s,"
        "\"graphics_context\":%s,\"depth_edge_pass\":%s}\n",
        kProducerId,
        kExtensionVersion,
        static_cast<unsigned long>(snapshot.process_id),
        static_cast<unsigned long long>(snapshot.process_creation_filetime_utc),
        executable_json.data(),
        snapshot.executable_sha256,
        entries_json.data(),
        active_json.data(),
        context_json.data(),
        depth_edge_json.data()
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
    const std::uint32_t iat_rva
) noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0
        || library_name == nullptr || symbol_name == nullptr
        || library_name[0] == '\0' || symbol_name[0] == '\0') {
        return ERROR_INVALID_STATE;
    }
    AcquireSRWLockExclusive(&g_state_lock);
    HRESULT result = StringCchCopyA(
        g_status.library_name,
        std::size(g_status.library_name),
        library_name
    );
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

void ObserveGraphicsPresent() noexcept {
    if (InterlockedCompareExchange(&g_started, 0, 0) == 0) {
        return;
    }
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
