#include "event_channel.h"
#include "world_map_capture.h"

#include <Windows.h>

#include <cstdint>
#include <cstdio>

namespace {

std::uint64_t FileTimeValue(const FILETIME value) noexcept {
    ULARGE_INTEGER combined{};
    combined.LowPart = value.dwLowDateTime;
    combined.HighPart = value.dwHighDateTime;
    return combined.QuadPart;
}

int Fail(const wchar_t* operation, const DWORD error) noexcept {
    ::fwprintf(stderr, L"%s failed with Win32 error %lu\n", operation, error);
    wonderbane::extension::ShutdownEventChannel();
    return 1;
}

}  // namespace

int wmain() {
    static_assert(
        wonderbane::extension::kWorldMapActionTestInputTag == 0x53424C54U
    );
    static_assert(wonderbane::extension::IsAcceptedWorldMapPointerInput(0U, 0U));
    static_assert(!wonderbane::extension::IsAcceptedWorldMapPointerInput(
        LLMHF_INJECTED,
        0U
    ));
    static_assert(wonderbane::extension::IsWorldMapActionTestInput(
        LLMHF_INJECTED,
        wonderbane::extension::kWorldMapActionTestInputTag
    ));
    static_assert(!wonderbane::extension::IsAcceptedWorldMapPointerInput(
        LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED,
        wonderbane::extension::kWorldMapActionTestInputTag
    ));
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
        return Fail(L"GetProcessTimes", GetLastError());
    }
    const wonderbane::extension::ProcessIdentity identity{
        GetCurrentProcessId(),
        FileTimeValue(creation_time),
    };
    DWORD result = wonderbane::extension::InitializeEventChannel(
        identity,
        wonderbane::extension::kWorldMapDestinationCapability
    );
    if (result != ERROR_SUCCESS) {
        return Fail(L"InitializeEventChannel", result);
    }
    wchar_t mapping_name[wonderbane::extension::kKernelObjectNameCapacity]{};
    result = wonderbane::extension::FormatEventMappingName(
        identity,
        mapping_name,
        wonderbane::extension::kKernelObjectNameCapacity
    );
    if (result != ERROR_SUCCESS) {
        return Fail(L"FormatEventMappingName", result);
    }
    const HANDLE mapping = OpenFileMappingW(
        FILE_MAP_READ | FILE_MAP_WRITE,
        FALSE,
        mapping_name
    );
    if (mapping == nullptr) {
        return Fail(L"OpenFileMappingW", GetLastError());
    }
    auto* storage = static_cast<wonderbane::extension::EventChannelStorage*>(
        MapViewOfFile(
            mapping,
            FILE_MAP_READ | FILE_MAP_WRITE,
            0U,
            0U,
            sizeof(wonderbane::extension::EventChannelStorage)
        )
    );
    if (storage == nullptr) {
        result = GetLastError();
        CloseHandle(mapping);
        return Fail(L"MapViewOfFile", result);
    }
    InterlockedExchange(
        &storage->header.consumer_process_id,
        static_cast<LONG>(GetCurrentProcessId())
    );
    InterlockedExchange64(
        &storage->header.consumer_heartbeat_tick,
        static_cast<LONG64>(GetTickCount64())
    );

    FILETIME captured{};
    GetSystemTimeAsFileTime(&captured);
    const wonderbane::extension::WorldMapDestination event{
        wonderbane::extension::kRightPointerButton,
        FileTimeValue(captured),
        9001U,
        106662.5,
        52432.25,
        0x0123456789ABCDEFULL,
        400,
        300,
        380,
        260,
    };
    if (!wonderbane::extension::TryPublishWorldMapDestination(event)) {
        UnmapViewOfFile(storage);
        CloseHandle(mapping);
        return Fail(L"TryPublishWorldMapDestination", ERROR_INVALID_DATA);
    }
    const auto& first = storage->slots[0];
    if (
        storage->header.write_sequence != 1
        || storage->header.read_sequence != 0
        || first.committed_sequence != 1
        || first.kind != wonderbane::extension::kWorldMapDestinationKind
        || first.button != event.button
        || first.window_handle != event.window_handle
        || first.lt != event.lt
        || first.lg != event.lg
        || first.snapshot_hash != event.snapshot_hash
        || first.desktop_screen_x != event.desktop_screen_x
        || first.desktop_screen_y != event.desktop_screen_y
        || first.client_x != event.client_x
        || first.client_y != event.client_y
    ) {
        UnmapViewOfFile(storage);
        CloseHandle(mapping);
        return Fail(L"published event validation", ERROR_INVALID_DATA);
    }

    InterlockedExchange64(&storage->header.read_sequence, 1);
    for (std::uint32_t index = 0U; index < wonderbane::extension::kEventChannelCapacity; ++index) {
        if (!wonderbane::extension::TryPublishWorldMapDestination(event)) {
            UnmapViewOfFile(storage);
            CloseHandle(mapping);
            return Fail(L"bounded event publication", ERROR_INVALID_DATA);
        }
    }
    if (
        wonderbane::extension::TryPublishWorldMapDestination(event)
        || storage->header.dropped_event_count != 1
        || storage->header.producer_error != ERROR_NOT_ENOUGH_QUOTA
    ) {
        UnmapViewOfFile(storage);
        CloseHandle(mapping);
        return Fail(L"full channel fail-open validation", ERROR_INVALID_DATA);
    }

    UnmapViewOfFile(storage);
    CloseHandle(mapping);
    wonderbane::extension::ShutdownEventChannel();
    return 0;
}
