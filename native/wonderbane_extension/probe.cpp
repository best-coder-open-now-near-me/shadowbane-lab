#include "extension_api.h"
#include "event_channel.h"

#include <Windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using InitializeFunction = DWORD(WINAPI*)();
using GetStatusFunction = DWORD(WINAPI*)(WonderBaneExtensionStatusV1*);

int Fail(const wchar_t* operation, const DWORD error) noexcept {
    ::fwprintf(stderr, L"%s failed with Win32 error %lu\n", operation, error);
    return 1;
}

std::uint64_t FileTimeValue(const FILETIME value) noexcept {
    ULARGE_INTEGER combined{};
    combined.LowPart = value.dwLowDateTime;
    combined.HighPart = value.dwHighDateTime;
    return combined.QuadPart;
}

DWORD VerifyEventChannel() noexcept {
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
    const wonderbane::extension::ProcessIdentity identity{
        GetCurrentProcessId(),
        FileTimeValue(creation_time),
    };
    wchar_t mapping_name[wonderbane::extension::kKernelObjectNameCapacity]{};
    DWORD result = wonderbane::extension::FormatEventMappingName(
        identity,
        mapping_name,
        wonderbane::extension::kKernelObjectNameCapacity
    );
    if (result != ERROR_SUCCESS) {
        return result;
    }
    const HANDLE mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, mapping_name);
    if (mapping == nullptr) {
        return GetLastError();
    }
    const auto* storage = static_cast<const wonderbane::extension::EventChannelStorage*>(
        MapViewOfFile(
            mapping,
            FILE_MAP_READ,
            0U,
            0U,
            sizeof(wonderbane::extension::EventChannelStorage)
        )
    );
    if (storage == nullptr) {
        result = GetLastError();
        CloseHandle(mapping);
        return result;
    }
    const bool valid = (
        std::memcmp(
            storage->header.magic,
            wonderbane::extension::kEventChannelMagic,
            sizeof(wonderbane::extension::kEventChannelMagic)
        ) == 0
        && storage->header.schema_version
            == wonderbane::extension::kEventChannelSchemaVersion
        && storage->header.header_size == wonderbane::extension::kEventChannelHeaderSize
        && storage->header.slot_size == wonderbane::extension::kEventChannelSlotSize
        && storage->header.capacity == wonderbane::extension::kEventChannelCapacity
        && storage->header.process_id == identity.process_id
        && storage->header.process_creation_filetime_utc
            == identity.creation_filetime_utc
        && storage->header.capability_flags == 0U
    );
    UnmapViewOfFile(storage);
    CloseHandle(mapping);
    return valid ? ERROR_SUCCESS : ERROR_INVALID_DATA;
}

}  // namespace

int wmain(const int argument_count, wchar_t** arguments) {
    if (argument_count != 2) {
        ::fwprintf(stderr, L"usage: wonderbane_extension_probe <extension.dll>\n");
        return 2;
    }
    const HMODULE module = LoadLibraryExW(
        arguments[1],
        nullptr,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32
    );
    if (module == nullptr) {
        return Fail(L"LoadLibraryExW", GetLastError());
    }

    const auto initialize = reinterpret_cast<InitializeFunction>(
        GetProcAddress(module, "WonderBaneExtensionInitialize")
    );
    const auto get_status = reinterpret_cast<GetStatusFunction>(
        GetProcAddress(module, "WonderBaneExtensionGetStatus")
    );
    if (initialize == nullptr || get_status == nullptr) {
        const DWORD error = GetLastError();
        FreeLibrary(module);
        return Fail(L"GetProcAddress", error);
    }
    DWORD result = initialize();
    if (result != ERROR_SUCCESS) {
        FreeLibrary(module);
        return Fail(L"WonderBaneExtensionInitialize", result);
    }
    result = initialize();
    if (result != ERROR_SUCCESS) {
        FreeLibrary(module);
        return Fail(L"idempotent WonderBaneExtensionInitialize", result);
    }

    WonderBaneExtensionStatusV1 status{};
    status.structure_size = sizeof(status);
    result = get_status(&status);
    if (result != ERROR_SUCCESS) {
        FreeLibrary(module);
        return Fail(L"WonderBaneExtensionGetStatus", result);
    }
    if (
        status.abi_version != WONDERBANE_EXTENSION_ABI_VERSION
        || status.state != static_cast<std::uint32_t>(WonderBaneExtensionState::initialized)
        || status.initialization_result != ERROR_SUCCESS
        || status.process_id != GetCurrentProcessId()
        || status.heartbeat_path[0] == L'\0'
    ) {
        FreeLibrary(module);
        return Fail(L"status validation", ERROR_INVALID_DATA);
    }
    result = VerifyEventChannel();
    if (result != ERROR_SUCCESS) {
        FreeLibrary(module);
        return Fail(L"event channel validation", result);
    }
    const DWORD heartbeat_attributes = GetFileAttributesW(status.heartbeat_path);
    if (
        heartbeat_attributes == INVALID_FILE_ATTRIBUTES
        || (heartbeat_attributes & FILE_ATTRIBUTE_DIRECTORY) != 0U
        || (heartbeat_attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0U
    ) {
        FreeLibrary(module);
        return Fail(L"heartbeat validation", ERROR_INVALID_DATA);
    }

    ::wprintf(L"%s\n", status.heartbeat_path);
    if (FreeLibrary(module) == FALSE) {
        return Fail(L"FreeLibrary", GetLastError());
    }
    HMODULE resident_module = nullptr;
    if (GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
                | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCWSTR>(module),
            &resident_module
        ) == FALSE) {
        return Fail(L"pinned module residency", GetLastError());
    }
    if (resident_module != module) {
        return Fail(L"pinned module identity", ERROR_INVALID_HANDLE);
    }
    return 0;
}
