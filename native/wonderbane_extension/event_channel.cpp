#include "event_channel.h"

#include <strsafe.h>

#include <cmath>
#include <cstring>
#include <limits>

namespace wonderbane::extension {
namespace {

HANDLE g_mapping = nullptr;
HANDLE g_signal = nullptr;
EventChannelStorage* g_storage = nullptr;
constexpr ULONGLONG kMaximumConsumerAgeMilliseconds = 1000U;

DWORD HResultToWin32(const HRESULT result) noexcept {
    if (HRESULT_FACILITY(result) == FACILITY_WIN32) {
        return HRESULT_CODE(result);
    }
    return ERROR_GEN_FAILURE;
}

void RecordProducerError(const DWORD error) noexcept {
    if (g_storage != nullptr) {
        InterlockedExchange(
            &g_storage->header.producer_error,
            static_cast<LONG>(error)
        );
    }
}

void RecordDroppedEvent() noexcept {
    if (g_storage != nullptr) {
        InterlockedIncrement64(&g_storage->header.dropped_event_count);
    }
}

bool EventIsValid(const WorldMapDestination& event) noexcept {
    return (
        (event.button == kLeftPointerButton || event.button == kRightPointerButton)
        && event.captured_at_filetime_utc > 0U
        && event.window_handle > 0U
        && std::isfinite(event.lt)
        && std::isfinite(event.lg)
        && event.lt >= 0.0
        && event.lg >= 0.0
        && event.lt <= static_cast<double>(std::numeric_limits<std::uint32_t>::max())
        && event.lg <= static_cast<double>(std::numeric_limits<std::uint32_t>::max())
    );
}

bool ConsumerLeaseIsActive() noexcept {
    if (g_storage == nullptr) {
        return false;
    }
    const LONG consumer_process_id = InterlockedCompareExchange(
        &g_storage->header.consumer_process_id,
        0,
        0
    );
    const LONG64 heartbeat_tick = InterlockedCompareExchange64(
        &g_storage->header.consumer_heartbeat_tick,
        0,
        0
    );
    if (consumer_process_id <= 0 || heartbeat_tick <= 0) {
        return false;
    }
    const ULONGLONG now = GetTickCount64();
    return now >= static_cast<ULONGLONG>(heartbeat_tick)
        && now - static_cast<ULONGLONG>(heartbeat_tick)
            <= kMaximumConsumerAgeMilliseconds;
}

}  // namespace

DWORD FormatEventMappingName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"Local\\ShadowbaneLab.Extension.Events.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

DWORD FormatEventSignalName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        destination_capacity,
        L"Local\\ShadowbaneLab.Extension.Signal.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result) ? ERROR_SUCCESS : HResultToWin32(result);
}

DWORD InitializeEventChannel(
    const ProcessIdentity& identity,
    const std::uint32_t capability_flags
) noexcept {
    if (
        identity.process_id == 0U
        || identity.creation_filetime_utc == 0U
        || g_mapping != nullptr
        || g_signal != nullptr
        || g_storage != nullptr
        || (
            capability_flags
            & ~(kWorldMapDestinationCapability | kTaggedTestInputCapability)
        ) != 0U
    ) {
        return ERROR_INVALID_STATE;
    }
    wchar_t mapping_name[kKernelObjectNameCapacity]{};
    wchar_t signal_name[kKernelObjectNameCapacity]{};
    DWORD result = FormatEventMappingName(
        identity,
        mapping_name,
        kKernelObjectNameCapacity
    );
    if (result != ERROR_SUCCESS) {
        return result;
    }
    result = FormatEventSignalName(identity, signal_name, kKernelObjectNameCapacity);
    if (result != ERROR_SUCCESS) {
        return result;
    }

    g_mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0U,
        static_cast<DWORD>(sizeof(EventChannelStorage)),
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
    g_storage = static_cast<EventChannelStorage*>(MapViewOfFile(
        g_mapping,
        FILE_MAP_READ | FILE_MAP_WRITE,
        0U,
        0U,
        sizeof(EventChannelStorage)
    ));
    if (g_storage == nullptr) {
        result = GetLastError();
        CloseHandle(g_mapping);
        g_mapping = nullptr;
        return result;
    }
    g_signal = CreateEventW(nullptr, FALSE, FALSE, signal_name);
    if (g_signal == nullptr || GetLastError() == ERROR_ALREADY_EXISTS) {
        result = g_signal == nullptr ? GetLastError() : ERROR_ALREADY_EXISTS;
        if (g_signal != nullptr) {
            CloseHandle(g_signal);
            g_signal = nullptr;
        }
        UnmapViewOfFile(g_storage);
        g_storage = nullptr;
        CloseHandle(g_mapping);
        g_mapping = nullptr;
        return result;
    }

    ZeroMemory(g_storage, sizeof(EventChannelStorage));
    std::memcpy(g_storage->header.magic, kEventChannelMagic, sizeof(kEventChannelMagic));
    g_storage->header.schema_version = kEventChannelSchemaVersion;
    g_storage->header.header_size = kEventChannelHeaderSize;
    g_storage->header.slot_size = kEventChannelSlotSize;
    g_storage->header.capacity = kEventChannelCapacity;
    g_storage->header.process_id = identity.process_id;
    g_storage->header.capability_flags = capability_flags;
    g_storage->header.process_creation_filetime_utc = identity.creation_filetime_utc;
    MemoryBarrier();
    return ERROR_SUCCESS;
}

void ShutdownEventChannel() noexcept {
    if (g_signal != nullptr) {
        CloseHandle(g_signal);
        g_signal = nullptr;
    }
    if (g_storage != nullptr) {
        UnmapViewOfFile(g_storage);
        g_storage = nullptr;
    }
    if (g_mapping != nullptr) {
        CloseHandle(g_mapping);
        g_mapping = nullptr;
    }
}

bool TryPublishWorldMapDestination(
    const WorldMapDestination& event,
    const bool require_active_consumer
) noexcept {
    if (g_storage == nullptr || g_signal == nullptr) {
        return false;
    }
    if (!EventIsValid(event)) {
        RecordProducerError(ERROR_INVALID_DATA);
        return false;
    }
    if (require_active_consumer && !ConsumerLeaseIsActive()) {
        return false;
    }
    const LONG64 write_sequence = InterlockedCompareExchange64(
        &g_storage->header.write_sequence,
        0,
        0
    );
    const LONG64 read_sequence = InterlockedCompareExchange64(
        &g_storage->header.read_sequence,
        0,
        0
    );
    if (
        write_sequence < 0
        || read_sequence < 0
        || read_sequence > write_sequence
        || write_sequence == std::numeric_limits<LONG64>::max()
    ) {
        RecordProducerError(ERROR_INVALID_DATA);
        RecordDroppedEvent();
        return false;
    }
    if (write_sequence - read_sequence >= static_cast<LONG64>(kEventChannelCapacity)) {
        RecordProducerError(ERROR_NOT_ENOUGH_QUOTA);
        RecordDroppedEvent();
        return false;
    }

    const LONG64 sequence = write_sequence + 1;
    const std::size_t slot_index = static_cast<std::size_t>(
        write_sequence % static_cast<LONG64>(kEventChannelCapacity)
    );
    WorldMapDestinationSlot& slot = g_storage->slots[slot_index];
    InterlockedExchange64(&slot.committed_sequence, 0);
    slot.kind = kWorldMapDestinationKind;
    slot.button = event.button;
    slot.captured_at_filetime_utc = event.captured_at_filetime_utc;
    slot.window_handle = event.window_handle;
    slot.lt = event.lt;
    slot.lg = event.lg;
    slot.snapshot_hash = event.snapshot_hash;
    slot.desktop_screen_x = event.desktop_screen_x;
    slot.desktop_screen_y = event.desktop_screen_y;
    slot.client_x = event.client_x;
    slot.client_y = event.client_y;
    ZeroMemory(slot.reserved, sizeof(slot.reserved));
    MemoryBarrier();
    InterlockedExchange64(&slot.committed_sequence, sequence);
    InterlockedExchange64(&g_storage->header.write_sequence, sequence);
    InterlockedExchange(&g_storage->header.producer_error, ERROR_SUCCESS);
    if (SetEvent(g_signal) == FALSE) {
        RecordProducerError(GetLastError());
    }
    return true;
}

}  // namespace wonderbane::extension
