#include "camera_observation.h"
#include "cel_shading.h"
#include "extension_api.h"
#include "event_channel.h"
#include "graphics_control.h"
#include "graphics_status.h"
#include "performance_telemetry.h"
#include "world_map_capture.h"

#include <KnownFolders.h>
#include <ShlObj.h>
#include <strsafe.h>

#include <cstddef>
#include <cstdint>

namespace {

constexpr wchar_t kProductDirectory[] = L"ShadowbaneLab";
constexpr wchar_t kExtensionDirectory[] = L"client-extension";
constexpr std::size_t kPathCapacity = WONDERBANE_EXTENSION_HEARTBEAT_PATH_CAPACITY;
constexpr std::size_t kJsonCapacity = 768;
constexpr LONG kMaximumInitializationPolls = 500;
constexpr DWORD kInitializationPollMilliseconds = 10;
constexpr char kExtensionVersion[] = "1.6.10";
constexpr wchar_t kClientExecutableName[] = L"sb.exe";
constexpr wchar_t kPerformanceProfileEnvironment[] = L"WONDERBANE_PERFORMANCE_PROFILE";
constexpr std::size_t kPerformanceProfileCapacity = 16U;
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
constexpr bool kDiagnosticsOnly = true;
#else
constexpr bool kDiagnosticsOnly = false;
#endif

volatile LONG g_state = static_cast<LONG>(WonderBaneExtensionState::uninitialized);
volatile LONG g_initialization_result = ERROR_SUCCESS;
wchar_t g_heartbeat_path[kPathCapacity]{};
HMODULE g_extension_module = nullptr;

DWORD HResultToWin32(const HRESULT result) noexcept {
    if (HRESULT_FACILITY(result) == FACILITY_WIN32) {
        return HRESULT_CODE(result);
    }
    return ERROR_GEN_FAILURE;
}

DWORD RequireOrdinaryDirectory(const wchar_t* path) noexcept {
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
    wchar_t* destination,
    const std::size_t destination_capacity,
    const wchar_t* parent,
    const wchar_t* leaf
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

std::uint64_t FileTimeValue(const FILETIME value) noexcept {
    ULARGE_INTEGER combined{};
    combined.LowPart = value.dwLowDateTime;
    combined.HighPart = value.dwHighDateTime;
    return combined.QuadPart;
}

DWORD WriteAll(const HANDLE file, const char* data, const DWORD length) noexcept {
    DWORD total_written = 0;
    while (total_written < length) {
        DWORD written = 0;
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

DWORD IsClientExecutable(bool* const is_client) noexcept {
    if (is_client == nullptr) {
        return ERROR_INVALID_PARAMETER;
    }
    wchar_t executable_path[kPathCapacity]{};
    const DWORD length = GetModuleFileNameW(
        nullptr,
        executable_path,
        static_cast<DWORD>(kPathCapacity)
    );
    if (length == 0U) {
        return GetLastError();
    }
    if (length >= kPathCapacity) {
        return ERROR_INSUFFICIENT_BUFFER;
    }
    const wchar_t* file_name = executable_path;
    for (const wchar_t* cursor = executable_path; *cursor != L'\0'; ++cursor) {
        if (*cursor == L'\\' || *cursor == L'/') {
            file_name = cursor + 1;
        }
    }
    *is_client = CompareStringOrdinal(
        file_name,
        -1,
        kClientExecutableName,
        -1,
        TRUE
    ) == CSTR_EQUAL;
    return ERROR_SUCCESS;
}

DWORD ReadProcessIdentity(
    wonderbane::extension::ProcessIdentity* const identity
) noexcept {
    if (identity == nullptr) {
        return ERROR_INVALID_PARAMETER;
    }
    FILETIME creation_time{};
    FILETIME exit_time{};
    FILETIME kernel_time{};
    FILETIME user_time{};
    if (GetProcessTimes(
            GetCurrentProcess(),
            &creation_time,
            &exit_time,
            &kernel_time,
            &user_time
        ) == FALSE) {
        return GetLastError();
    }
    identity->process_id = GetCurrentProcessId();
    identity->creation_filetime_utc = FileTimeValue(creation_time);
    if (identity->process_id == 0U || identity->creation_filetime_utc == 0U) {
        return ERROR_INVALID_DATA;
    }
    return ERROR_SUCCESS;
}

DWORD PinExtensionModule() noexcept {
    if (g_extension_module == nullptr) {
        return ERROR_INVALID_HANDLE;
    }
    HMODULE pinned_module = nullptr;
    const DWORD flags = (
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
        | GET_MODULE_HANDLE_EX_FLAG_PIN
    );
    if (GetModuleHandleExW(
            flags,
            reinterpret_cast<LPCWSTR>(g_extension_module),
            &pinned_module
        ) == FALSE) {
        return GetLastError();
    }
    return pinned_module == g_extension_module
        ? ERROR_SUCCESS
        : ERROR_INVALID_HANDLE;
}

DWORD ReadPerformanceTelemetryProfile(
    wonderbane::extension::PerformanceTelemetryProfile* const profile
) noexcept {
    if (profile == nullptr) {
        return ERROR_INVALID_PARAMETER;
    }
    wchar_t value[kPerformanceProfileCapacity]{};
    SetLastError(ERROR_SUCCESS);
    const DWORD length = GetEnvironmentVariableW(
        kPerformanceProfileEnvironment,
        value,
        static_cast<DWORD>(kPerformanceProfileCapacity)
    );
    if (length == 0U) {
        const DWORD error = GetLastError();
        if (error == ERROR_ENVVAR_NOT_FOUND) {
            return wonderbane::extension::SelectPerformanceTelemetryProfile(nullptr, profile);
        }
        if (error != ERROR_SUCCESS) {
            return error;
        }
    }
    if (length >= kPerformanceProfileCapacity) {
        return ERROR_INSUFFICIENT_BUFFER;
    }
    return wonderbane::extension::SelectPerformanceTelemetryProfile(value, profile);
}

DWORD WriteHeartbeat(
    const wonderbane::extension::ProcessIdentity& identity
) noexcept {
    PWSTR local_app_data = nullptr;
    const HRESULT known_folder_result = SHGetKnownFolderPath(
        FOLDERID_LocalAppData,
        KF_FLAG_CREATE,
        nullptr,
        &local_app_data
    );
    if (FAILED(known_folder_result)) {
        return HResultToWin32(known_folder_result);
    }

    wchar_t product_directory[kPathCapacity]{};
    wchar_t extension_directory[kPathCapacity]{};
    wchar_t final_path[kPathCapacity]{};
    wchar_t temporary_path[kPathCapacity]{};
    DWORD result = CombinePath(
        product_directory,
        kPathCapacity,
        local_app_data,
        kProductDirectory
    );
    CoTaskMemFree(local_app_data);
    local_app_data = nullptr;
    if (result != ERROR_SUCCESS) {
        return result;
    }
    result = RequireOrdinaryDirectory(product_directory);
    if (result != ERROR_SUCCESS) {
        return result;
    }
    result = CombinePath(
        extension_directory,
        kPathCapacity,
        product_directory,
        kExtensionDirectory
    );
    if (result != ERROR_SUCCESS) {
        return result;
    }
    result = RequireOrdinaryDirectory(extension_directory);
    if (result != ERROR_SUCCESS) {
        return result;
    }

    FILETIME initialized_time{};
    GetSystemTimeAsFileTime(&initialized_time);
    const std::uint64_t initialized_value = FileTimeValue(initialized_time);

    HRESULT format_result = StringCchPrintfW(
        final_path,
        kPathCapacity,
        L"%s\\heartbeat-%lu-%llu.json",
        extension_directory,
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    if (FAILED(format_result)) {
        return HResultToWin32(format_result);
    }
    format_result = StringCchPrintfW(
        temporary_path,
        kPathCapacity,
        L"%s\\.heartbeat-%lu-%lu-%llu.tmp",
        extension_directory,
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long>(GetCurrentThreadId()),
        static_cast<unsigned long long>(GetTickCount64())
    );
    if (FAILED(format_result)) {
        return HResultToWin32(format_result);
    }

    char json[kJsonCapacity]{};
    format_result = StringCchPrintfA(
        json,
        kJsonCapacity,
        "{\"schema_version\":1,\"abi_version\":1,"
        "\"extension_version\":\"%s\",\"process_id\":%lu,"
        "\"process_creation_filetime_utc\":%llu,"
        "\"initialized_at_filetime_utc\":%llu,\"status\":\"initialized\"}\n",
        kExtensionVersion,
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc),
        static_cast<unsigned long long>(initialized_value)
    );
    if (FAILED(format_result)) {
        return HResultToWin32(format_result);
    }

    const HANDLE file = CreateFileW(
        temporary_path,
        GENERIC_WRITE,
        0,
        nullptr,
        CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL,
        nullptr
    );
    if (file == INVALID_HANDLE_VALUE) {
        return GetLastError();
    }
    result = WriteAll(file, json, static_cast<DWORD>(lstrlenA(json)));
    if (result == ERROR_SUCCESS && FlushFileBuffers(file) == FALSE) {
        result = GetLastError();
    }
    if (CloseHandle(file) == FALSE && result == ERROR_SUCCESS) {
        result = GetLastError();
    }
    if (result != ERROR_SUCCESS) {
        DeleteFileW(temporary_path);
        return result;
    }
    if (MoveFileExW(
            temporary_path,
            final_path,
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
        ) == FALSE) {
        result = GetLastError();
        DeleteFileW(temporary_path);
        return result;
    }
    format_result = StringCchCopyW(g_heartbeat_path, kPathCapacity, final_path);
    return SUCCEEDED(format_result) ? ERROR_SUCCESS : HResultToWin32(format_result);
}

}  // namespace

extern "C" DWORD WINAPI WonderBaneExtensionInitialize() noexcept {
    const LONG initializing = static_cast<LONG>(WonderBaneExtensionState::initializing);
    const LONG previous = InterlockedCompareExchange(
        &g_state,
        initializing,
        static_cast<LONG>(WonderBaneExtensionState::uninitialized)
    );
    if (previous == static_cast<LONG>(WonderBaneExtensionState::uninitialized)) {
        wonderbane::extension::ProcessIdentity identity{};
        wonderbane::extension::PerformanceTelemetryProfile performance_profile{};
        DWORD result = ReadProcessIdentity(&identity);
        bool is_client = false;
        if (result == ERROR_SUCCESS) {
            result = IsClientExecutable(&is_client);
        }
        const bool world_map_supported = (
            result == ERROR_SUCCESS
            && is_client
            && !kDiagnosticsOnly
            && wonderbane::extension::IsReviewedWorldMapClient()
        );
        bool event_channel_started = false;
        bool world_map_started = false;
        bool graphics_control_started = false;
        bool graphics_status_started = false;
        bool renderer_started = false;
        bool camera_observation_started = false;
        bool performance_telemetry_started = false;
        if (result == ERROR_SUCCESS && !kDiagnosticsOnly) {
            result = wonderbane::extension::InitializeEventChannel(
                identity,
                world_map_supported
                    ? (
                        wonderbane::extension::kWorldMapDestinationCapability
                        | wonderbane::extension::kTaggedTestInputCapability
                    )
                    : 0U
            );
            event_channel_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS) {
            result = PinExtensionModule();
        }
        if (result == ERROR_SUCCESS && world_map_supported) {
            result = wonderbane::extension::StartWorldMapCapture(
                g_extension_module,
                identity
            );
            world_map_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS && is_client) {
            result = wonderbane::extension::StartGraphicsStatusPublication();
            graphics_status_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS && is_client && !kDiagnosticsOnly) {
            result = wonderbane::extension::StartGraphicsControl();
            graphics_control_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS && is_client) {
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
            result = wonderbane::extension::StartGraphicsPresentObservation();
#else
            result = wonderbane::extension::StartStrongCelShading();
#endif
            renderer_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS && is_client && kDiagnosticsOnly) {
            result = wonderbane::extension::StartPassiveCameraObservation();
            camera_observation_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS && is_client) {
            result = ReadPerformanceTelemetryProfile(&performance_profile);
        }
        if (
            result == ERROR_SUCCESS
            && is_client
            && performance_profile
                != wonderbane::extension::PerformanceTelemetryProfile::disabled
        ) {
            result = wonderbane::extension::StartPerformanceTelemetry(
                identity,
                performance_profile
            );
            performance_telemetry_started = result == ERROR_SUCCESS;
        }
        if (result == ERROR_SUCCESS) {
            result = WriteHeartbeat(identity);
        }
        if (result != ERROR_SUCCESS) {
            if (performance_telemetry_started) {
                wonderbane::extension::StopPerformanceTelemetry();
            }
            if (camera_observation_started) {
                wonderbane::extension::StopPassiveCameraObservation();
            }
            if (renderer_started) {
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
                wonderbane::extension::StopGraphicsPresentObservation();
#else
                wonderbane::extension::StopStrongCelShading();
#endif
            }
            if (graphics_control_started) {
                wonderbane::extension::StopGraphicsControl();
            }
            if (graphics_status_started) {
                wonderbane::extension::StopGraphicsStatusPublication();
            }
            if (world_map_started) {
                wonderbane::extension::StopWorldMapCapture();
            }
            if (event_channel_started) {
                wonderbane::extension::ShutdownEventChannel();
            }
        }
        InterlockedExchange(&g_initialization_result, static_cast<LONG>(result));
        InterlockedExchange(
            &g_state,
            static_cast<LONG>(
                result == ERROR_SUCCESS
                    ? WonderBaneExtensionState::initialized
                    : WonderBaneExtensionState::failed
            )
        );
        return result;
    }

    for (LONG poll = 0; poll < kMaximumInitializationPolls; ++poll) {
        const LONG state = InterlockedCompareExchange(&g_state, 0, 0);
        if (state != initializing) {
            return static_cast<DWORD>(InterlockedCompareExchange(
                &g_initialization_result,
                0,
                0
            ));
        }
        Sleep(kInitializationPollMilliseconds);
    }
    return ERROR_TIMEOUT;
}

extern "C" DWORD WINAPI WonderBaneExtensionGetStatus(
    WonderBaneExtensionStatusV1* status
) noexcept {
    if (status == nullptr || status->structure_size < sizeof(WonderBaneExtensionStatusV1)) {
        return ERROR_INSUFFICIENT_BUFFER;
    }
    WonderBaneExtensionStatusV1 snapshot{};
    snapshot.structure_size = sizeof(WonderBaneExtensionStatusV1);
    snapshot.abi_version = WONDERBANE_EXTENSION_ABI_VERSION;
    snapshot.extension_version_major = WONDERBANE_EXTENSION_VERSION_MAJOR;
    snapshot.extension_version_minor = WONDERBANE_EXTENSION_VERSION_MINOR;
    snapshot.extension_version_patch = WONDERBANE_EXTENSION_VERSION_PATCH;
    snapshot.state = static_cast<std::uint32_t>(InterlockedCompareExchange(&g_state, 0, 0));
    snapshot.initialization_result = static_cast<std::uint32_t>(InterlockedCompareExchange(
        &g_initialization_result,
        0,
        0
    ));
    snapshot.process_id = GetCurrentProcessId();
    const HRESULT copy_result = StringCchCopyW(
        snapshot.heartbeat_path,
        WONDERBANE_EXTENSION_HEARTBEAT_PATH_CAPACITY,
        g_heartbeat_path
    );
    if (FAILED(copy_result)) {
        return HResultToWin32(copy_result);
    }
    *status = snapshot;
    return ERROR_SUCCESS;
}

BOOL APIENTRY DllMain(
    const HMODULE module,
    const DWORD reason,
    LPVOID
) noexcept {
    if (reason == DLL_PROCESS_ATTACH) {
        g_extension_module = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
