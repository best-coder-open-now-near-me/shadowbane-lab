#pragma once

#include "client_action_dispatch.h"
#include "event_channel.h"

#include <Windows.h>
#include <strsafe.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace wonderbane::extension {

constexpr char kClientActionChannelMagic[8] = {'W', 'B', 'A', 'C', 'T', 'V', '1', '\0'};
constexpr std::uint32_t kClientActionChannelSchemaVersion = 1U;
constexpr std::uint32_t kClientActionChannelHeaderSize = 128U;
constexpr std::uint32_t kClientActionCommandSlotSize = 192U;
constexpr std::uint32_t kClientActionCommandCapacity = 32U;
constexpr std::uint32_t kClientActionResultSlotSize = 128U;
constexpr std::uint32_t kClientActionResultCapacity = 64U;
constexpr std::uint32_t kClientActionPayloadVersion = 1U;
constexpr std::size_t kClientActionArgumentCapacity = 96U;
constexpr std::size_t kClientActionPowerIdentifierCapacity = 32U;
constexpr std::size_t kClientActionResultDetailCapacity = 72U;
constexpr ULONGLONG kMaximumActionHostLeaseAgeMilliseconds = 1000U;
constexpr DWORD kActionCommandWorkerPollMilliseconds = 100U;
constexpr std::size_t kClientActionCommandRingOffset = kClientActionChannelHeaderSize;
constexpr std::size_t kClientActionResultRingOffset =
    kClientActionCommandRingOffset
    + kClientActionCommandSlotSize * kClientActionCommandCapacity;
constexpr std::size_t kClientActionChannelSize =
    kClientActionResultRingOffset
    + kClientActionResultSlotSize * kClientActionResultCapacity;

#pragma pack(push, 1)
struct ClientActionChannelHeader {
    char magic[8];
    std::uint32_t schema_version;
    std::uint32_t header_size;
    std::uint32_t command_slot_size;
    std::uint32_t command_capacity;
    std::uint32_t result_slot_size;
    std::uint32_t result_capacity;
    std::uint32_t process_id;
    std::uint32_t capability_flags;
    std::uint64_t process_creation_filetime_utc;
    volatile LONG64 command_write_sequence;
    volatile LONG64 command_read_sequence;
    volatile LONG64 result_write_sequence;
    volatile LONG64 result_read_sequence;
    volatile LONG64 dropped_command_count;
    volatile LONG64 dropped_result_count;
    volatile LONG host_process_id;
    volatile LONG host_lease_generation;
    volatile LONG64 host_heartbeat_tick;
    volatile LONG consumer_thread_id;
    volatile LONG last_error;
    std::uint8_t reserved[8];
};

struct ClientActionCommandSlot {
    volatile LONG64 committed_sequence;
    std::uint64_t command_id;
    std::uint32_t kind;
    std::uint32_t payload_version;
    std::uint64_t created_tick;
    std::uint64_t deadline_tick;
    std::int32_t action_code;
    std::int32_t parameter_one;
    std::int32_t parameter_two;
    std::uint32_t argument_length;
    std::uint32_t power_identifier_length;
    std::uint32_t flags;
    char argument[kClientActionArgumentCapacity];
    char power_identifier[kClientActionPowerIdentifierCapacity];
};

struct ClientActionResultSlot {
    volatile LONG64 committed_sequence;
    std::uint64_t command_id;
    LONG64 command_sequence;
    std::uint32_t stage;
    std::uint32_t error;
    std::uint64_t observed_tick;
    std::uint32_t consumer_thread_id;
    std::uint32_t detail_length;
    char detail[kClientActionResultDetailCapacity];
    std::uint8_t reserved[8];
};

struct ClientActionChannelStorage {
    ClientActionChannelHeader header;
    ClientActionCommandSlot commands[kClientActionCommandCapacity];
    ClientActionResultSlot results[kClientActionResultCapacity];
};
#pragma pack(pop)

static_assert(sizeof(ClientActionChannelHeader) == kClientActionChannelHeaderSize);
static_assert(sizeof(ClientActionCommandSlot) == kClientActionCommandSlotSize);
static_assert(sizeof(ClientActionResultSlot) == kClientActionResultSlotSize);
static_assert(sizeof(ClientActionChannelStorage) == kClientActionChannelSize);
static_assert(offsetof(ClientActionChannelHeader, command_write_sequence) % 8U == 0U);
static_assert(offsetof(ClientActionChannelHeader, result_write_sequence) % 8U == 0U);
static_assert(offsetof(ClientActionChannelHeader, host_heartbeat_tick) % 8U == 0U);
static_assert(offsetof(ClientActionCommandSlot, committed_sequence) == 0U);
static_assert(offsetof(ClientActionResultSlot, committed_sequence) == 0U);

namespace command_channel_detail {

struct Runtime {
    HANDLE mapping = nullptr;
    HANDLE command_signal = nullptr;
    HANDLE result_signal = nullptr;
    HANDLE stop_signal = nullptr;
    HANDLE worker = nullptr;
    ClientActionChannelStorage* storage = nullptr;
};

inline Runtime g_runtime{};

inline DWORD HResultToWin32(const HRESULT result) noexcept {
    return HRESULT_FACILITY(result) == FACILITY_WIN32
        ? HRESULT_CODE(result)
        : ERROR_GEN_FAILURE;
}

inline bool HeaderIsValid(const ClientActionChannelHeader& header) noexcept {
    return (
        std::memcmp(header.magic, kClientActionChannelMagic, sizeof(kClientActionChannelMagic))
            == 0
        && header.schema_version == kClientActionChannelSchemaVersion
        && header.header_size == kClientActionChannelHeaderSize
        && header.command_slot_size == kClientActionCommandSlotSize
        && header.command_capacity == kClientActionCommandCapacity
        && header.result_slot_size == kClientActionResultSlotSize
        && header.result_capacity == kClientActionResultCapacity
        && header.process_id != 0U
        && header.process_creation_filetime_utc != 0U
        && (header.capability_flags & ~kKnownClientActionCapabilities) == 0U
        && (header.capability_flags & kClientActionTransportCapability) != 0U
    );
}

inline bool HostLeaseIsActive(
    ClientActionChannelStorage& storage,
    const ULONGLONG now
) noexcept {
    const LONG process_id = InterlockedCompareExchange(
        &storage.header.host_process_id,
        0,
        0
    );
    const LONG64 heartbeat = InterlockedCompareExchange64(
        &storage.header.host_heartbeat_tick,
        0,
        0
    );
    return (
        process_id > 0
        && heartbeat > 0
        && now >= static_cast<ULONGLONG>(heartbeat)
        && now - static_cast<ULONGLONG>(heartbeat)
            <= kMaximumActionHostLeaseAgeMilliseconds
    );
}

inline bool TextIsValid(
    const char* const value,
    const std::uint32_t length,
    const std::size_t capacity,
    const bool allow_empty
) noexcept {
    if (value == nullptr || length > capacity || (!allow_empty && length == 0U)) {
        return false;
    }
    for (std::uint32_t index = 0U; index < length; ++index) {
        const unsigned char character = static_cast<unsigned char>(value[index]);
        if (character < 0x20U || character > 0x7EU) {
            return false;
        }
    }
    return true;
}

inline bool PowerIdentifierIsValid(
    const char* const value,
    const std::uint32_t length
) noexcept {
    if (!TextIsValid(value, length, kClientActionPowerIdentifierCapacity, false)) {
        return false;
    }
    for (std::uint32_t index = 0U; index < length; ++index) {
        const char character = value[index];
        if (
            !(
                (character >= 'A' && character <= 'Z')
                || (character >= '0' && character <= '9')
                || character == '-'
                || character == '_'
            )
        ) {
            return false;
        }
    }
    return true;
}

struct ValidationResult {
    DWORD error;
    const char* detail;
    std::size_t detail_length;
};

inline ValidationResult ValidateCommand(
    const ClientActionCommandSlot& command,
    const ULONGLONG now
) noexcept {
    static constexpr char kInvalidPayloadVersion[] = "unsupported_command_payload_version";
    static constexpr char kInvalidCommandId[] = "invalid_command_id";
    static constexpr char kInvalidDeadline[] = "invalid_command_deadline";
    static constexpr char kExpired[] = "command_deadline_expired";
    static constexpr char kInvalidFlags[] = "unsupported_command_flags";
    static constexpr char kInvalidAction[] = "invalid_native_action_payload";
    static constexpr char kInvalidPower[] = "invalid_learned_power_payload";
    static constexpr char kUnknownKind[] = "unsupported_client_action_kind";

    if (command.payload_version != kClientActionPayloadVersion) {
        return {ERROR_REVISION_MISMATCH, kInvalidPayloadVersion, sizeof(kInvalidPayloadVersion) - 1U};
    }
    if (command.command_id == 0U) {
        return {ERROR_INVALID_DATA, kInvalidCommandId, sizeof(kInvalidCommandId) - 1U};
    }
    if (command.created_tick == 0U || command.deadline_tick < command.created_tick) {
        return {ERROR_INVALID_DATA, kInvalidDeadline, sizeof(kInvalidDeadline) - 1U};
    }
    if (now > command.deadline_tick) {
        return {ERROR_TIMEOUT, kExpired, sizeof(kExpired) - 1U};
    }
    if (command.flags != 0U) {
        return {ERROR_NOT_SUPPORTED, kInvalidFlags, sizeof(kInvalidFlags) - 1U};
    }

    const auto kind = static_cast<ClientActionKind>(command.kind);
    if (kind == ClientActionKind::native_action) {
        if (
            command.action_code <= 0
            || command.power_identifier_length != 0U
            || !TextIsValid(
                command.argument,
                command.argument_length,
                kClientActionArgumentCapacity,
                true
            )
        ) {
            return {ERROR_INVALID_DATA, kInvalidAction, sizeof(kInvalidAction) - 1U};
        }
        return {ERROR_SUCCESS, nullptr, 0U};
    }
    if (kind == ClientActionKind::learned_power) {
        if (
            command.action_code != 0
            || command.parameter_one != 0
            || command.parameter_two != 0
            || command.argument_length != 0U
            || !PowerIdentifierIsValid(
                command.power_identifier,
                command.power_identifier_length
            )
        ) {
            return {ERROR_INVALID_DATA, kInvalidPower, sizeof(kInvalidPower) - 1U};
        }
        return {ERROR_SUCCESS, nullptr, 0U};
    }
    return {ERROR_NOT_SUPPORTED, kUnknownKind, sizeof(kUnknownKind) - 1U};
}

inline bool TryPublishResult(
    ClientActionChannelStorage& storage,
    const HANDLE result_signal,
    const LONG64 command_sequence,
    const std::uint64_t command_id,
    const ClientActionResultStage stage,
    const DWORD error,
    const char* const detail,
    const std::size_t detail_length,
    const ULONGLONG now
) noexcept {
    const LONG64 write_sequence = InterlockedCompareExchange64(
        &storage.header.result_write_sequence,
        0,
        0
    );
    const LONG64 read_sequence = InterlockedCompareExchange64(
        &storage.header.result_read_sequence,
        0,
        0
    );
    if (
        write_sequence < 0
        || read_sequence < 0
        || read_sequence > write_sequence
        || write_sequence == std::numeric_limits<LONG64>::max()
    ) {
        InterlockedExchange(&storage.header.last_error, ERROR_INVALID_DATA);
        InterlockedIncrement64(&storage.header.dropped_result_count);
        return false;
    }
    if (
        write_sequence - read_sequence
        >= static_cast<LONG64>(kClientActionResultCapacity)
    ) {
        InterlockedExchange(&storage.header.last_error, ERROR_NOT_ENOUGH_QUOTA);
        InterlockedIncrement64(&storage.header.dropped_result_count);
        return false;
    }
    if (detail_length > kClientActionResultDetailCapacity) {
        InterlockedExchange(&storage.header.last_error, ERROR_INSUFFICIENT_BUFFER);
        return false;
    }

    const LONG64 sequence = write_sequence + 1;
    const std::size_t slot_index = static_cast<std::size_t>(
        write_sequence % static_cast<LONG64>(kClientActionResultCapacity)
    );
    ClientActionResultSlot& slot = storage.results[slot_index];
    InterlockedExchange64(&slot.committed_sequence, 0);
    slot.command_id = command_id;
    slot.command_sequence = command_sequence;
    slot.stage = static_cast<std::uint32_t>(stage);
    slot.error = error;
    slot.observed_tick = now;
    slot.consumer_thread_id = GetCurrentThreadId();
    slot.detail_length = static_cast<std::uint32_t>(detail_length);
    ZeroMemory(slot.detail, sizeof(slot.detail));
    if (detail != nullptr && detail_length > 0U) {
        std::memcpy(slot.detail, detail, detail_length);
    }
    ZeroMemory(slot.reserved, sizeof(slot.reserved));
    MemoryBarrier();
    InterlockedExchange64(&slot.committed_sequence, sequence);
    InterlockedExchange64(&storage.header.result_write_sequence, sequence);
    InterlockedExchange(
        &storage.header.consumer_thread_id,
        static_cast<LONG>(GetCurrentThreadId())
    );
    InterlockedExchange(&storage.header.last_error, ERROR_SUCCESS);
    if (result_signal != nullptr && SetEvent(result_signal) == FALSE) {
        InterlockedExchange(
            &storage.header.last_error,
            static_cast<LONG>(GetLastError())
        );
    }
    return true;
}

inline DWORD DrainCommands(
    ClientActionChannelStorage& storage,
    const HANDLE result_signal,
    const ULONGLONG now
) noexcept {
    if (!HeaderIsValid(storage.header)) {
        return ERROR_INVALID_DATA;
    }
    if (!HostLeaseIsActive(storage, now)) {
        return ERROR_NO_DATA;
    }

    while (true) {
        const LONG64 write_sequence = InterlockedCompareExchange64(
            &storage.header.command_write_sequence,
            0,
            0
        );
        const LONG64 read_sequence = InterlockedCompareExchange64(
            &storage.header.command_read_sequence,
            0,
            0
        );
        if (
            write_sequence < 0
            || read_sequence < 0
            || read_sequence > write_sequence
            || write_sequence - read_sequence
                > static_cast<LONG64>(kClientActionCommandCapacity)
        ) {
            return ERROR_INVALID_DATA;
        }
        if (read_sequence == write_sequence) {
            return ERROR_SUCCESS;
        }

        const LONG64 expected_sequence = read_sequence + 1;
        const std::size_t slot_index = static_cast<std::size_t>(
            read_sequence % static_cast<LONG64>(kClientActionCommandCapacity)
        );
        ClientActionCommandSlot& slot = storage.commands[slot_index];
        if (
            InterlockedCompareExchange64(&slot.committed_sequence, 0, 0)
            != expected_sequence
        ) {
            return ERROR_RETRY;
        }
        ClientActionCommandSlot snapshot{};
        std::memcpy(&snapshot, &slot, sizeof(snapshot));
        MemoryBarrier();
        if (
            InterlockedCompareExchange64(&slot.committed_sequence, 0, 0)
            != expected_sequence
        ) {
            return ERROR_RETRY;
        }

        const ValidationResult validation = ValidateCommand(snapshot, now);
        ClientActionDispatchResult dispatch{};
        if (validation.error != ERROR_SUCCESS) {
            dispatch = {
                ClientActionResultStage::failed,
                validation.error,
                validation.detail,
                validation.detail_length,
                GetCurrentThreadId(),
            };
        } else {
            const ClientActionRequest request{
                snapshot.command_id,
                static_cast<ClientActionKind>(snapshot.kind),
                snapshot.action_code,
                snapshot.parameter_one,
                snapshot.parameter_two,
                snapshot.argument,
                snapshot.argument_length,
                snapshot.power_identifier,
                snapshot.power_identifier_length,
            };
            dispatch = DispatchClientAction(request);
        }
        if (
            !TryPublishResult(
                storage,
                result_signal,
                expected_sequence,
                snapshot.command_id,
                dispatch.stage,
                dispatch.error,
                dispatch.detail,
                dispatch.detail_length,
                now
            )
        ) {
            return ERROR_NOT_ENOUGH_QUOTA;
        }
        InterlockedExchange64(
            &storage.header.command_read_sequence,
            expected_sequence
        );
    }
}

inline DWORD WINAPI WorkerThread(void*) noexcept {
    Runtime& runtime = g_runtime;
    const HANDLE handles[2] = {runtime.stop_signal, runtime.command_signal};
    while (true) {
        const DWORD wait_result = WaitForMultipleObjects(
            2U,
            handles,
            FALSE,
            kActionCommandWorkerPollMilliseconds
        );
        if (wait_result == WAIT_OBJECT_0) {
            return ERROR_SUCCESS;
        }
        if (wait_result != WAIT_OBJECT_0 + 1U && wait_result != WAIT_TIMEOUT) {
            if (runtime.storage != nullptr) {
                InterlockedExchange(
                    &runtime.storage->header.last_error,
                    ERROR_GEN_FAILURE
                );
            }
            return ERROR_GEN_FAILURE;
        }
        if (runtime.storage == nullptr) {
            return ERROR_INVALID_HANDLE;
        }
        const DWORD drain_result = DrainCommands(
            *runtime.storage,
            runtime.result_signal,
            GetTickCount64()
        );
        if (
            drain_result != ERROR_SUCCESS
            && drain_result != ERROR_NO_DATA
            && drain_result != ERROR_RETRY
            && drain_result != ERROR_NOT_ENOUGH_QUOTA
        ) {
            InterlockedExchange(
                &runtime.storage->header.last_error,
                static_cast<LONG>(drain_result)
            );
        }
    }
}

inline void CloseRuntime() noexcept {
    Runtime& runtime = g_runtime;
    if (runtime.worker != nullptr) {
        CloseHandle(runtime.worker);
        runtime.worker = nullptr;
    }
    if (runtime.stop_signal != nullptr) {
        CloseHandle(runtime.stop_signal);
        runtime.stop_signal = nullptr;
    }
    if (runtime.result_signal != nullptr) {
        CloseHandle(runtime.result_signal);
        runtime.result_signal = nullptr;
    }
    if (runtime.command_signal != nullptr) {
        CloseHandle(runtime.command_signal);
        runtime.command_signal = nullptr;
    }
    if (runtime.storage != nullptr) {
        UnmapViewOfFile(runtime.storage);
        runtime.storage = nullptr;
    }
    if (runtime.mapping != nullptr) {
        CloseHandle(runtime.mapping);
        runtime.mapping = nullptr;
    }
}

}  // namespace command_channel_detail

inline DWORD FormatClientActionMappingName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"Local\\ShadowbaneLab.Extension.Actions.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result)
        ? ERROR_SUCCESS
        : command_channel_detail::HResultToWin32(result);
}

inline DWORD FormatClientActionCommandSignalName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"Local\\ShadowbaneLab.Extension.ActionCommand.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result)
        ? ERROR_SUCCESS
        : command_channel_detail::HResultToWin32(result);
}

inline DWORD FormatClientActionResultSignalName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"Local\\ShadowbaneLab.Extension.ActionResult.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result)
        ? ERROR_SUCCESS
        : command_channel_detail::HResultToWin32(result);
}

inline DWORD StartClientActionCommandChannel(
    const ProcessIdentity& identity
) noexcept {
    using namespace command_channel_detail;
    Runtime& runtime = g_runtime;
    if (
        identity.process_id == 0U
        || identity.creation_filetime_utc == 0U
        || runtime.mapping != nullptr
        || runtime.command_signal != nullptr
        || runtime.result_signal != nullptr
        || runtime.stop_signal != nullptr
        || runtime.worker != nullptr
        || runtime.storage != nullptr
    ) {
        return ERROR_INVALID_STATE;
    }

    wchar_t mapping_name[kKernelObjectNameCapacity]{};
    wchar_t command_signal_name[kKernelObjectNameCapacity]{};
    wchar_t result_signal_name[kKernelObjectNameCapacity]{};
    DWORD result = FormatClientActionMappingName(
        identity,
        mapping_name,
        kKernelObjectNameCapacity
    );
    if (result == ERROR_SUCCESS) {
        result = FormatClientActionCommandSignalName(
            identity,
            command_signal_name,
            kKernelObjectNameCapacity
        );
    }
    if (result == ERROR_SUCCESS) {
        result = FormatClientActionResultSignalName(
            identity,
            result_signal_name,
            kKernelObjectNameCapacity
        );
    }
    if (result != ERROR_SUCCESS) {
        return result;
    }

    runtime.mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0U,
        static_cast<DWORD>(sizeof(ClientActionChannelStorage)),
        mapping_name
    );
    if (runtime.mapping == nullptr) {
        return GetLastError();
    }
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseRuntime();
        return ERROR_ALREADY_EXISTS;
    }
    runtime.storage = static_cast<ClientActionChannelStorage*>(MapViewOfFile(
        runtime.mapping,
        FILE_MAP_READ | FILE_MAP_WRITE,
        0U,
        0U,
        sizeof(ClientActionChannelStorage)
    ));
    if (runtime.storage == nullptr) {
        result = GetLastError();
        CloseRuntime();
        return result;
    }
    runtime.command_signal = CreateEventW(
        nullptr,
        FALSE,
        FALSE,
        command_signal_name
    );
    if (
        runtime.command_signal == nullptr
        || GetLastError() == ERROR_ALREADY_EXISTS
    ) {
        result = runtime.command_signal == nullptr
            ? GetLastError()
            : ERROR_ALREADY_EXISTS;
        CloseRuntime();
        return result;
    }
    runtime.result_signal = CreateEventW(
        nullptr,
        FALSE,
        FALSE,
        result_signal_name
    );
    if (
        runtime.result_signal == nullptr
        || GetLastError() == ERROR_ALREADY_EXISTS
    ) {
        result = runtime.result_signal == nullptr
            ? GetLastError()
            : ERROR_ALREADY_EXISTS;
        CloseRuntime();
        return result;
    }
    runtime.stop_signal = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (runtime.stop_signal == nullptr) {
        result = GetLastError();
        CloseRuntime();
        return result;
    }

    ZeroMemory(runtime.storage, sizeof(ClientActionChannelStorage));
    std::memcpy(
        runtime.storage->header.magic,
        kClientActionChannelMagic,
        sizeof(kClientActionChannelMagic)
    );
    runtime.storage->header.schema_version = kClientActionChannelSchemaVersion;
    runtime.storage->header.header_size = kClientActionChannelHeaderSize;
    runtime.storage->header.command_slot_size = kClientActionCommandSlotSize;
    runtime.storage->header.command_capacity = kClientActionCommandCapacity;
    runtime.storage->header.result_slot_size = kClientActionResultSlotSize;
    runtime.storage->header.result_capacity = kClientActionResultCapacity;
    runtime.storage->header.process_id = identity.process_id;
    runtime.storage->header.capability_flags = ReviewedClientActionCapabilities();
    runtime.storage->header.process_creation_filetime_utc = identity.creation_filetime_utc;
    MemoryBarrier();

    runtime.worker = CreateThread(
        nullptr,
        0U,
        WorkerThread,
        nullptr,
        0U,
        nullptr
    );
    if (runtime.worker == nullptr) {
        result = GetLastError();
        CloseRuntime();
        return result;
    }
    return ERROR_SUCCESS;
}

inline void StopClientActionCommandChannel() noexcept {
    using namespace command_channel_detail;
    Runtime& runtime = g_runtime;
    if (runtime.stop_signal != nullptr) {
        SetEvent(runtime.stop_signal);
    }
    if (runtime.worker != nullptr) {
        (void)WaitForSingleObject(runtime.worker, 2000U);
    }
    CloseRuntime();
}

inline DWORD DrainClientActionCommandsForTesting(
    ClientActionChannelStorage& storage,
    const ULONGLONG now
) noexcept {
    return command_channel_detail::DrainCommands(storage, nullptr, now);
}

inline bool ValidateClientActionChannelHeaderForTesting(
    const ClientActionChannelHeader& header
) noexcept {
    return command_channel_detail::HeaderIsValid(header);
}

}  // namespace wonderbane::extension
