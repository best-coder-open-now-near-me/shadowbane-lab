#pragma once

#include <Windows.h>

#include <cstdint>

#define WONDERBANE_EXTENSION_ABI_VERSION 1U
#define WONDERBANE_EXTENSION_VERSION_MAJOR 1U
#define WONDERBANE_EXTENSION_VERSION_MINOR 4U
#define WONDERBANE_EXTENSION_VERSION_PATCH 5U
#define WONDERBANE_EXTENSION_HEARTBEAT_PATH_CAPACITY 1024U

enum class WonderBaneExtensionState : std::uint32_t {
    uninitialized = 0,
    initializing = 1,
    initialized = 2,
    failed = 3,
};

struct WonderBaneExtensionStatusV1 {
    std::uint32_t structure_size;
    std::uint32_t abi_version;
    std::uint32_t extension_version_major;
    std::uint32_t extension_version_minor;
    std::uint32_t extension_version_patch;
    std::uint32_t state;
    std::uint32_t initialization_result;
    std::uint32_t process_id;
    wchar_t heartbeat_path[WONDERBANE_EXTENSION_HEARTBEAT_PATH_CAPACITY];
};

extern "C" DWORD WINAPI WonderBaneExtensionInitialize() noexcept;
extern "C" DWORD WINAPI WonderBaneExtensionGetStatus(
    WonderBaneExtensionStatusV1* status
) noexcept;
