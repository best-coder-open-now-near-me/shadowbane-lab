#include "command_channel.h"
#include "event_channel.h"
#include "world_map_capture.h"

#include <Windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

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

bool ResultDetailEquals(
    const wonderbane::extension::ClientActionResultSlot& result,
    const char* const expected
) noexcept {
    const std::size_t length = std::strlen(expected);
    return (
        result.detail_length == length
        && std::memcmp(result.detail, expected, length) == 0
    );
}

void InitializeLocalActionStorage(
    wonderbane::extension::ClientActionChannelStorage* const storage,
    const wonderbane::extension::ProcessIdentity& identity
) noexcept {
    ZeroMemory(storage, sizeof(*storage));
    std::memcpy(
        storage->header.magic,
        wonderbane::extension::kClientActionChannelMagic,
        sizeof(wonderbane::extension::kClientActionChannelMagic)
    );
    storage->header.schema_version =
        wonderbane::extension::kClientActionChannelSchemaVersion;
    storage->header.header_size = wonderbane::extension::kClientActionChannelHeaderSize;
    storage->header.command_slot_size =
        wonderbane::extension::kClientActionCommandSlotSize;
    storage->header.command_capacity =
        wonderbane::extension::kClientActionCommandCapacity;
    storage->header.result_slot_size =
        wonderbane::extension::kClientActionResultSlotSize;
    storage->header.result_capacity =
        wonderbane::extension::kClientActionResultCapacity;
    storage->header.process_id = identity.process_id;
    storage->header.capability_flags =
        wonderbane::extension::ReviewedClientActionCapabilities();
    storage->header.process_creation_filetime_utc = identity.creation_filetime_utc;
    storage->header.host_process_id = static_cast<LONG>(GetCurrentProcessId());
    storage->header.host_heartbeat_tick = static_cast<LONG64>(GetTickCount64());
}

void PublishLocalCommand(
    wonderbane::extension::ClientActionChannelStorage* const storage,
    const LONG64 sequence,
    const std::uint64_t command_id,
    const wonderbane::extension::ClientActionKind kind,
    const std::uint64_t created_tick,
    const std::uint64_t deadline_tick,
    const std::int32_t action_code,
    const char* const power_identifier
) noexcept {
    const std::size_t slot_index = static_cast<std::size_t>(
        (sequence - 1) % wonderbane::extension::kClientActionCommandCapacity
    );
    auto& command = storage->commands[slot_index];
    ZeroMemory(&command, sizeof(command));
    command.command_id = command_id;
    command.kind = static_cast<std::uint32_t>(kind);
    command.payload_version = wonderbane::extension::kClientActionPayloadVersion;
    command.created_tick = created_tick;
    command.deadline_tick = deadline_tick;
    command.action_code = action_code;
    if (power_identifier != nullptr) {
        const std::size_t length = std::strlen(power_identifier);
        command.power_identifier_length = static_cast<std::uint32_t>(length);
        std::memcpy(command.power_identifier, power_identifier, length);
    }
    command.committed_sequence = sequence;
    storage->header.command_write_sequence = sequence;
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
    static_assert(
        wonderbane::extension::ReviewedClientActionCapabilities()
        == wonderbane::extension::kClientActionTransportCapability
    );

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

    wchar_t action_mapping_name[wonderbane::extension::kKernelObjectNameCapacity]{};
    result = wonderbane::extension::FormatClientActionMappingName(
        identity,
        action_mapping_name,
        wonderbane::extension::kKernelObjectNameCapacity
    );
    if (result != ERROR_SUCCESS) {
        return Fail(L"FormatClientActionMappingName", result);
    }
    const HANDLE action_mapping = OpenFileMappingW(
        FILE_MAP_READ | FILE_MAP_WRITE,
        FALSE,
        action_mapping_name
    );
    if (action_mapping == nullptr) {
        return Fail(L"OpenFileMappingW(action)", GetLastError());
    }
    auto* mapped_action_storage =
        static_cast<wonderbane::extension::ClientActionChannelStorage*>(MapViewOfFile(
            action_mapping,
            FILE_MAP_READ | FILE_MAP_WRITE,
            0U,
            0U,
            sizeof(wonderbane::extension::ClientActionChannelStorage)
        ));
    if (mapped_action_storage == nullptr) {
        result = GetLastError();
        CloseHandle(action_mapping);
        return Fail(L"MapViewOfFile(action)", result);
    }
    if (
        !wonderbane::extension::ValidateClientActionChannelHeaderForTesting(
            mapped_action_storage->header
        )
        || mapped_action_storage->header.process_id != identity.process_id
        || mapped_action_storage->header.process_creation_filetime_utc
            != identity.creation_filetime_utc
        || mapped_action_storage->header.capability_flags
            != wonderbane::extension::kClientActionTransportCapability
    ) {
        UnmapViewOfFile(mapped_action_storage);
        CloseHandle(action_mapping);
        return Fail(L"client action mapping header", ERROR_INVALID_DATA);
    }
    UnmapViewOfFile(mapped_action_storage);
    CloseHandle(action_mapping);

    wonderbane::extension::ClientActionChannelStorage action_storage{};
    InitializeLocalActionStorage(&action_storage, identity);
    const ULONGLONG action_now = GetTickCount64();
    PublishLocalCommand(
        &action_storage,
        1,
        1001U,
        wonderbane::extension::ClientActionKind::native_action,
        action_now,
        action_now + 1000U,
        188,
        nullptr
    );
    result = wonderbane::extension::DrainClientActionCommandsForTesting(
        action_storage,
        action_now
    );
    const auto& native_result = action_storage.results[0];
    if (
        result != ERROR_SUCCESS
        || action_storage.header.command_read_sequence != 1
        || action_storage.header.result_write_sequence != 1
        || native_result.command_id != 1001U
        || native_result.command_sequence != 1
        || native_result.stage
            != static_cast<std::uint32_t>(
                wonderbane::extension::ClientActionResultStage::failed
            )
        || native_result.error != ERROR_NOT_SUPPORTED
        || !ResultDetailEquals(
            native_result,
            "reviewed_client_dispatcher_unavailable"
        )
    ) {
        return Fail(L"native action fail-closed dispatch", ERROR_INVALID_DATA);
    }

    action_storage.header.result_read_sequence = 1;
    const ULONGLONG power_now = GetTickCount64();
    action_storage.header.host_heartbeat_tick = static_cast<LONG64>(power_now);
    PublishLocalCommand(
        &action_storage,
        2,
        1002U,
        wonderbane::extension::ClientActionKind::learned_power,
        power_now,
        power_now + 1000U,
        0,
        "ASS-013"
    );
    result = wonderbane::extension::DrainClientActionCommandsForTesting(
        action_storage,
        power_now
    );
    const auto& power_result = action_storage.results[1];
    if (
        result != ERROR_SUCCESS
        || power_result.command_id != 1002U
        || power_result.command_sequence != 2
        || power_result.error != ERROR_NOT_SUPPORTED
        || !ResultDetailEquals(
            power_result,
            "reviewed_client_dispatcher_unavailable"
        )
    ) {
        return Fail(L"learned power fail-closed dispatch", ERROR_INVALID_DATA);
    }

    action_storage.header.result_read_sequence = 2;
    action_storage.header.host_heartbeat_tick = static_cast<LONG64>(GetTickCount64());
    PublishLocalCommand(
        &action_storage,
        3,
        1003U,
        wonderbane::extension::ClientActionKind::native_action,
        1U,
        2U,
        188,
        nullptr
    );
    result = wonderbane::extension::DrainClientActionCommandsForTesting(
        action_storage,
        GetTickCount64()
    );
    const auto& expired_result = action_storage.results[2];
    if (
        result != ERROR_SUCCESS
        || expired_result.error != ERROR_TIMEOUT
        || !ResultDetailEquals(expired_result, "command_deadline_expired")
    ) {
        return Fail(L"expired action command", ERROR_INVALID_DATA);
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
