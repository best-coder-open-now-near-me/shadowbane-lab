#pragma once

#include "event_channel.h"

#include <Windows.h>
#include <strsafe.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace wonderbane::extension {

constexpr char kClientActionTraceMagic[8] = {'W', 'B', 'A', 'C', 'T', 'R', '1', '\0'};
constexpr std::uint32_t kClientActionTraceSchemaVersion = 1U;
constexpr std::uint32_t kClientActionTraceHeaderSize = 128U;
constexpr std::uint32_t kClientActionTraceSlotSize = 192U;
constexpr std::uint32_t kClientActionTraceCapacity = 256U;
constexpr std::uint32_t kClientActionTraceArgumentCapacity = 32U;
constexpr std::uint32_t kClientActionTraceStackCapacity = 8U;
constexpr std::size_t kClientActionTraceSize =
    kClientActionTraceHeaderSize
    + kClientActionTraceSlotSize * kClientActionTraceCapacity;

constexpr std::uint32_t kClientActionTraceTransportCapability = 1U << 0U;
constexpr std::uint32_t kClientActionTraceCpuContextCapability = 1U << 1U;
constexpr std::uint32_t kClientActionTraceStackCapability = 1U << 2U;
constexpr std::uint32_t kClientActionTraceArcaneTupleCapability = 1U << 3U;
constexpr std::uint32_t kClientActionTraceCapabilities =
    kClientActionTraceTransportCapability
    | kClientActionTraceCpuContextCapability
    | kClientActionTraceStackCapability
    | kClientActionTraceArcaneTupleCapability;

constexpr std::uint32_t kClientActionTraceContextCompleteFlag = 1U << 0U;
constexpr std::uint32_t kClientActionTraceStackCompleteFlag = 1U << 1U;
constexpr std::uint32_t kClientActionTraceTupleCompleteFlag = 1U << 2U;
constexpr std::uint32_t kClientActionTraceArgumentPresentFlag = 1U << 3U;
constexpr std::uint32_t kClientActionTraceAction188CandidateFlag = 1U << 4U;
constexpr std::uint32_t kClientActionTraceKnownFlags =
    kClientActionTraceContextCompleteFlag
    | kClientActionTraceStackCompleteFlag
    | kClientActionTraceTupleCompleteFlag
    | kClientActionTraceArgumentPresentFlag
    | kClientActionTraceAction188CandidateFlag;

constexpr std::uint32_t kReviewedWonderBanePeTimestamp = 0x50A3A4E3U;
constexpr std::uint32_t kReviewedWonderBaneImageSize = 0x0063D000U;
constexpr std::uint32_t kReviewedWonderBanePreferredBase = 0x00400000U;
constexpr std::int32_t kTargetNextMobActionCode = 188;

enum class ClientActionTraceProbeStatus : std::uint32_t {
    unconfigured = 0U,
    profile_rejected = 1U,
    armed = 2U,
    observing = 3U,
    failed = 4U,
};

enum class ClientActionTraceRecordKind : std::uint32_t {
    call_entry = 1U,
};

#pragma pack(push, 1)
struct ClientActionTraceHeader {
    char magic[8];
    std::uint32_t schema_version;
    std::uint32_t header_size;
    std::uint32_t slot_size;
    std::uint32_t capacity;
    std::uint32_t process_id;
    std::uint32_t capability_flags;
    std::uint64_t process_creation_filetime_utc;
    std::uint64_t qpc_frequency;
    std::uint64_t started_qpc;
    volatile LONG64 write_sequence;
    volatile LONG64 overwritten_record_count;
    volatile LONG64 observed_record_count;
    volatile LONG producer_error;
    volatile LONG probe_status;
    std::uint32_t target_action_code;
    std::uint32_t configured_target_rva;
    std::uint32_t configured_callsite_rva;
    std::uint32_t configured_stack_dword_count;
    std::uint32_t active_probe_count;
    std::uint32_t reviewed_pe_timestamp;
    std::uint32_t reviewed_image_size;
    std::uint32_t reviewed_preferred_base;
    std::uint32_t reserved0;
    std::uint32_t reserved1;
};

struct ClientActionTraceSlot {
    volatile LONG64 committed_sequence;
    std::uint32_t kind;
    std::uint32_t flags;
    std::uint64_t observed_qpc;
    std::uint32_t thread_id;
    std::int32_t action_code;
    std::uint32_t target_rva;
    std::uint32_t caller_rva;
    std::uint32_t eax;
    std::uint32_t ebx;
    std::uint32_t ecx;
    std::uint32_t edx;
    std::uint32_t esi;
    std::uint32_t edi;
    std::uint32_t ebp;
    std::uint32_t esp;
    std::uint32_t eflags;
    std::int32_t parameter_one;
    std::int32_t parameter_two;
    std::uint32_t argument_length;
    std::uint32_t stack_dword_count;
    char argument[kClientActionTraceArgumentCapacity];
    std::uint32_t stack_dwords[kClientActionTraceStackCapacity];
    std::uint8_t reserved[36];
};

struct ClientActionTraceStorage {
    ClientActionTraceHeader header;
    ClientActionTraceSlot slots[kClientActionTraceCapacity];
};
#pragma pack(pop)

static_assert(sizeof(ClientActionTraceHeader) == kClientActionTraceHeaderSize);
static_assert(sizeof(ClientActionTraceSlot) == kClientActionTraceSlotSize);
static_assert(sizeof(ClientActionTraceStorage) == kClientActionTraceSize);
static_assert(offsetof(ClientActionTraceHeader, write_sequence) % alignof(LONG64) == 0U);

struct ClientActionTraceRecord {
    std::uint32_t flags;
    std::uint64_t observed_qpc;
    std::uint32_t thread_id;
    std::int32_t action_code;
    std::uint32_t target_rva;
    std::uint32_t caller_rva;
    std::uint32_t eax;
    std::uint32_t ebx;
    std::uint32_t ecx;
    std::uint32_t edx;
    std::uint32_t esi;
    std::uint32_t edi;
    std::uint32_t ebp;
    std::uint32_t esp;
    std::uint32_t eflags;
    std::int32_t parameter_one;
    std::int32_t parameter_two;
    std::uint32_t argument_length;
    std::uint32_t stack_dword_count;
    char argument[kClientActionTraceArgumentCapacity];
    std::uint32_t stack_dwords[kClientActionTraceStackCapacity];
};

namespace client_action_trace_detail {
inline HANDLE mapping = nullptr;
inline HANDLE signal = nullptr;
inline ClientActionTraceStorage* storage = nullptr;
inline SRWLOCK publish_lock = SRWLOCK_INIT;

inline DWORD HResultToWin32(const HRESULT value) noexcept {
    return HRESULT_FACILITY(value) == FACILITY_WIN32
        ? HRESULT_CODE(value)
        : ERROR_GEN_FAILURE;
}

inline void Close() noexcept {
    if (signal != nullptr) {
        CloseHandle(signal);
        signal = nullptr;
    }
    if (storage != nullptr) {
        UnmapViewOfFile(storage);
        storage = nullptr;
    }
    if (mapping != nullptr) {
        CloseHandle(mapping);
        mapping = nullptr;
    }
}

inline bool Printable(const char* const text, const std::uint32_t length) noexcept {
    for (std::uint32_t index = 0U; index < length; ++index) {
        const unsigned char value = static_cast<unsigned char>(text[index]);
        if (value < 0x20U || value > 0x7EU) {
            return false;
        }
    }
    return true;
}

inline bool Valid(const ClientActionTraceRecord& record) noexcept {
    const bool argument_present = record.argument_length > 0U;
    const bool stack_present = record.stack_dword_count > 0U;
    return (
        record.observed_qpc > 0U
        && record.thread_id > 0U
        && record.action_code == kTargetNextMobActionCode
        && record.target_rva < kReviewedWonderBaneImageSize
        && record.caller_rva < kReviewedWonderBaneImageSize
        && record.argument_length <= kClientActionTraceArgumentCapacity
        && record.stack_dword_count <= kClientActionTraceStackCapacity
        && (record.flags & ~kClientActionTraceKnownFlags) == 0U
        && (record.flags & kClientActionTraceContextCompleteFlag) != 0U
        && (record.flags & kClientActionTraceAction188CandidateFlag) != 0U
        && argument_present
            == ((record.flags & kClientActionTraceArgumentPresentFlag) != 0U)
        && stack_present
            == ((record.flags & kClientActionTraceStackCompleteFlag) != 0U)
        && (
            (record.flags & kClientActionTraceTupleCompleteFlag) != 0U
            || (
                record.parameter_one == 0
                && record.parameter_two == 0
                && !argument_present
            )
        )
        && Printable(record.argument, record.argument_length)
    );
}

inline DWORD Initialize(
    ClientActionTraceStorage* const target,
    const ProcessIdentity& identity,
    const std::uint64_t frequency,
    const std::uint64_t started
) noexcept {
    if (
        target == nullptr
        || identity.process_id == 0U
        || identity.creation_filetime_utc == 0U
        || frequency == 0U
        || started == 0U
    ) {
        return ERROR_INVALID_PARAMETER;
    }
    ZeroMemory(target, sizeof(*target));
    std::memcpy(target->header.magic, kClientActionTraceMagic, sizeof(kClientActionTraceMagic));
    target->header.schema_version = kClientActionTraceSchemaVersion;
    target->header.header_size = kClientActionTraceHeaderSize;
    target->header.slot_size = kClientActionTraceSlotSize;
    target->header.capacity = kClientActionTraceCapacity;
    target->header.process_id = identity.process_id;
    target->header.capability_flags = kClientActionTraceCapabilities;
    target->header.process_creation_filetime_utc = identity.creation_filetime_utc;
    target->header.qpc_frequency = frequency;
    target->header.started_qpc = started;
    target->header.probe_status =
        static_cast<LONG>(ClientActionTraceProbeStatus::unconfigured);
    target->header.target_action_code =
        static_cast<std::uint32_t>(kTargetNextMobActionCode);
    target->header.reviewed_pe_timestamp = kReviewedWonderBanePeTimestamp;
    target->header.reviewed_image_size = kReviewedWonderBaneImageSize;
    target->header.reviewed_preferred_base = kReviewedWonderBanePreferredBase;
    MemoryBarrier();
    return ERROR_SUCCESS;
}

inline bool Publish(
    ClientActionTraceStorage* const target,
    const ClientActionTraceRecord& record
) noexcept {
    if (target == nullptr || !Valid(record)) {
        if (target != nullptr) {
            InterlockedExchange(&target->header.producer_error, ERROR_INVALID_DATA);
        }
        return false;
    }
    AcquireSRWLockExclusive(&publish_lock);
    const LONG64 write = InterlockedCompareExchange64(
        &target->header.write_sequence,
        0,
        0
    );
    if (write < 0 || write == std::numeric_limits<LONG64>::max()) {
        InterlockedExchange(&target->header.producer_error, ERROR_ARITHMETIC_OVERFLOW);
        ReleaseSRWLockExclusive(&publish_lock);
        return false;
    }
    const LONG64 sequence = write + 1;
    ClientActionTraceSlot& slot = target->slots[
        static_cast<std::size_t>(
            write % static_cast<LONG64>(kClientActionTraceCapacity)
        )
    ];
    InterlockedExchange64(&slot.committed_sequence, 0);
    ZeroMemory(
        reinterpret_cast<std::uint8_t*>(&slot) + sizeof(slot.committed_sequence),
        sizeof(slot) - sizeof(slot.committed_sequence)
    );
    slot.kind = static_cast<std::uint32_t>(ClientActionTraceRecordKind::call_entry);
    slot.flags = record.flags;
    slot.observed_qpc = record.observed_qpc;
    slot.thread_id = record.thread_id;
    slot.action_code = record.action_code;
    slot.target_rva = record.target_rva;
    slot.caller_rva = record.caller_rva;
    slot.eax = record.eax;
    slot.ebx = record.ebx;
    slot.ecx = record.ecx;
    slot.edx = record.edx;
    slot.esi = record.esi;
    slot.edi = record.edi;
    slot.ebp = record.ebp;
    slot.esp = record.esp;
    slot.eflags = record.eflags;
    slot.parameter_one = record.parameter_one;
    slot.parameter_two = record.parameter_two;
    slot.argument_length = record.argument_length;
    slot.stack_dword_count = record.stack_dword_count;
    std::memcpy(slot.argument, record.argument, record.argument_length);
    std::memcpy(
        slot.stack_dwords,
        record.stack_dwords,
        sizeof(std::uint32_t) * record.stack_dword_count
    );
    MemoryBarrier();
    InterlockedExchange64(&slot.committed_sequence, sequence);
    InterlockedExchange64(&target->header.write_sequence, sequence);
    InterlockedExchange64(&target->header.observed_record_count, sequence);
    InterlockedExchange64(
        &target->header.overwritten_record_count,
        sequence > static_cast<LONG64>(kClientActionTraceCapacity)
            ? sequence - static_cast<LONG64>(kClientActionTraceCapacity)
            : 0
    );
    InterlockedExchange(&target->header.producer_error, ERROR_SUCCESS);
    ReleaseSRWLockExclusive(&publish_lock);
    return true;
}
}  // namespace client_action_trace_detail

inline DWORD FormatClientActionTraceMappingName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        capacity,
        L"Local\\ShadowbaneLab.Extension.ActionTrace.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result)
        ? ERROR_SUCCESS
        : client_action_trace_detail::HResultToWin32(result);
}

inline DWORD FormatClientActionTraceSignalName(
    const ProcessIdentity& identity,
    wchar_t* const destination,
    const std::size_t capacity
) noexcept {
    const HRESULT result = StringCchPrintfW(
        destination,
        capacity,
        L"Local\\ShadowbaneLab.Extension.ActionTraceSignal.%lu.%llu",
        static_cast<unsigned long>(identity.process_id),
        static_cast<unsigned long long>(identity.creation_filetime_utc)
    );
    return SUCCEEDED(result)
        ? ERROR_SUCCESS
        : client_action_trace_detail::HResultToWin32(result);
}

inline DWORD StartClientActionTraceChannel(const ProcessIdentity& identity) noexcept {
    using namespace client_action_trace_detail;
    if (
        identity.process_id == 0U
        || identity.creation_filetime_utc == 0U
        || mapping != nullptr
        || signal != nullptr
        || storage != nullptr
    ) {
        return ERROR_INVALID_STATE;
    }
    wchar_t mapping_name[kKernelObjectNameCapacity]{};
    wchar_t signal_name[kKernelObjectNameCapacity]{};
    DWORD result = FormatClientActionTraceMappingName(
        identity, mapping_name, kKernelObjectNameCapacity
    );
    if (result == ERROR_SUCCESS) {
        result = FormatClientActionTraceSignalName(
            identity, signal_name, kKernelObjectNameCapacity
        );
    }
    if (result != ERROR_SUCCESS) {
        return result;
    }
    SetLastError(ERROR_SUCCESS);
    mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0U,
        static_cast<DWORD>(sizeof(ClientActionTraceStorage)),
        mapping_name
    );
    if (mapping == nullptr || GetLastError() == ERROR_ALREADY_EXISTS) {
        result = mapping == nullptr ? GetLastError() : ERROR_ALREADY_EXISTS;
        Close();
        return result;
    }
    storage = static_cast<ClientActionTraceStorage*>(MapViewOfFile(
        mapping,
        FILE_MAP_READ | FILE_MAP_WRITE,
        0U,
        0U,
        sizeof(ClientActionTraceStorage)
    ));
    if (storage == nullptr) {
        result = GetLastError();
        Close();
        return result;
    }
    SetLastError(ERROR_SUCCESS);
    signal = CreateEventW(nullptr, FALSE, FALSE, signal_name);
    if (signal == nullptr || GetLastError() == ERROR_ALREADY_EXISTS) {
        result = signal == nullptr ? GetLastError() : ERROR_ALREADY_EXISTS;
        Close();
        return result;
    }
    LARGE_INTEGER frequency{};
    LARGE_INTEGER started{};
    if (
        QueryPerformanceFrequency(&frequency) == FALSE
        || QueryPerformanceCounter(&started) == FALSE
        || frequency.QuadPart <= 0
        || started.QuadPart <= 0
    ) {
        result = GetLastError();
        Close();
        return result == ERROR_SUCCESS ? ERROR_GEN_FAILURE : result;
    }
    result = Initialize(
        storage,
        identity,
        static_cast<std::uint64_t>(frequency.QuadPart),
        static_cast<std::uint64_t>(started.QuadPart)
    );
    if (result != ERROR_SUCCESS) {
        Close();
    }
    return result;
}

inline void StopClientActionTraceChannel() noexcept {
    client_action_trace_detail::Close();
}

inline bool TryPublishClientActionTrace(
    const ClientActionTraceRecord& record
) noexcept {
    using namespace client_action_trace_detail;
    if (storage == nullptr || signal == nullptr || !Publish(storage, record)) {
        return false;
    }
    if (SetEvent(signal) == FALSE) {
        InterlockedExchange(
            &storage->header.producer_error,
            static_cast<LONG>(GetLastError())
        );
    }
    return true;
}

inline DWORD InitializeClientActionTraceStorageForTesting(
    ClientActionTraceStorage* const storage,
    const ProcessIdentity& identity,
    const std::uint64_t frequency,
    const std::uint64_t started
) noexcept {
    return client_action_trace_detail::Initialize(
        storage, identity, frequency, started
    );
}

inline bool PublishClientActionTraceForTesting(
    ClientActionTraceStorage* const storage,
    const ClientActionTraceRecord& record
) noexcept {
    return client_action_trace_detail::Publish(storage, record);
}

inline bool ValidateClientActionTraceHeaderForTesting(
    const ClientActionTraceHeader& header
) noexcept {
    return (
        std::memcmp(header.magic, kClientActionTraceMagic, sizeof(kClientActionTraceMagic)) == 0
        && header.schema_version == kClientActionTraceSchemaVersion
        && header.header_size == kClientActionTraceHeaderSize
        && header.slot_size == kClientActionTraceSlotSize
        && header.capacity == kClientActionTraceCapacity
        && header.process_id > 0U
        && header.capability_flags == kClientActionTraceCapabilities
        && header.process_creation_filetime_utc > 0U
        && header.qpc_frequency > 0U
        && header.started_qpc > 0U
        && header.probe_status
            == static_cast<LONG>(ClientActionTraceProbeStatus::unconfigured)
        && header.target_action_code
            == static_cast<std::uint32_t>(kTargetNextMobActionCode)
        && header.configured_target_rva == 0U
        && header.configured_callsite_rva == 0U
        && header.configured_stack_dword_count == 0U
        && header.active_probe_count == 0U
        && header.reviewed_pe_timestamp == kReviewedWonderBanePeTimestamp
        && header.reviewed_image_size == kReviewedWonderBaneImageSize
        && header.reviewed_preferred_base == kReviewedWonderBanePreferredBase
        && header.reserved0 == 0U
        && header.reserved1 == 0U
    );
}

}  // namespace wonderbane::extension
