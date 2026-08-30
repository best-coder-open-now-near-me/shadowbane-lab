#include "extension_api.h"

#include <Windows.h>

#include <cstdio>

namespace {

using InitializeFunction = DWORD(WINAPI*)();
using GetStatusFunction = DWORD(WINAPI*)(WonderBaneExtensionStatusV1*);

int Fail(const wchar_t* operation, const DWORD error) noexcept {
    ::fwprintf(stderr, L"%s failed with Win32 error %lu\n", operation, error);
    return 1;
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
    return 0;
}
