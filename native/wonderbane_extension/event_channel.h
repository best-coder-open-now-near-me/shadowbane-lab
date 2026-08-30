#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

constexpr char kEventChannelMagic[8] = {'W', 'B', 'E', 'X', 'T', 'V', '1', '\0'};
constexpr std::uint32_t kEventChannelSchemaVersion = 1U;
constexpr std::uint32_t kEventChannelHeaderSize = 80U;
constexpr std::uint32_t kEventChannelSlotSize = 80U;
constexpr std::uint32_t kEventChannelCapacity = 64U;
constexpr std::uint32_t kWorldMapDestinationCapability = 1U << 0U;
constexpr std::uint32_t kWorldMapDestinationKind = 1U;
constexpr std::uint32_t kLeftPointerButton = 1U;
constexpr std::uint32_t kRightPointerButton = 2U;
constexpr std::size_t kEventChannelSize =
    kEventChannelHeaderSize + kEventChannelSlotSize * kEventChannelCapacity;
constexpr std::size_t kKernelObjectNameCapacity = 160U;

struct ProcessIdentity {
    DWORD process_id;
    std::uint64_t creation_filetime_utc;
};

#pragma pack(push, 1)
struct EventChannelHeader {
    char magic[8];
    std::uint32_t schema_version;
    std::uint32_t header_size;
    std::uint32_t slot_size;
    std::uint32_t capacity;
    std::uint32_t process_id;
    std::uint32_t capability_flags;
    std::uint64_t process_creation_filetime_utc;
    volatile LONG64 write_sequence;
    volatile LONG64 read_sequence;
    volatile LONG64 dropped_event_count;
    volatile LONG producer_error;
    std::uint8_t reserved[12];
};

struct WorldMapDestinationSlot {
    volatile LONG64 committed_sequence;
    std::uint32_t kind;
    std::uint32_t button;
    std::uint64_t captured_at_filetime_utc;
    std::uint64_t window_handle;
    double lt;
    double lg;
    std::uint64_t snapshot_hash;
    std::int32_t desktop_screen_x;
    std::int32_t desktop_screen_y;
    std::int32_t client_x;
    std::int32_t client_y;
    std::uint8_t reserved[8];
};

struct EventChannelStorage {
    EventChannelHeader header;
    WorldMapDestinationSlot slots[kEventChannelCapacity];
};
#pragma pack(pop)

static_assert(sizeof(EventChannelHeader) == kEventChannelHeaderSize);
static_assert(sizeof(WorldMapDestinationSlot) == kEventChannelSlotSize);
static_assert(sizeof(EventChannelStorage) == kEventChannelSize);
static_assert(offsetof(EventChannelHeader, write_sequence) % alignof(LONG64) == 0U);
static_assert(offsetof(EventChannelHeader, read_sequence) % alignof(LONG64) == 0U);
static_assert(offsetof(WorldMapDestinationSlot, committed_sequence) == 0U);

struct WorldMapDestination {
    std::uint32_t button;
    std::uint64_t captured_at_filetime_utc;
    std::uint64_t window_handle;
    double lt;
    double lg;
    std::uint64_t snapshot_hash;
    std::int32_t desktop_screen_x;
    std::int32_t desktop_screen_y;
    std::int32_t client_x;
    std::int32_t client_y;
};

DWORD FormatEventMappingName(
    const ProcessIdentity& identity,
    wchar_t* destination,
    std::size_t destination_capacity
) noexcept;
DWORD FormatEventSignalName(
    const ProcessIdentity& identity,
    wchar_t* destination,
    std::size_t destination_capacity
) noexcept;
DWORD InitializeEventChannel(const ProcessIdentity& identity) noexcept;
void ShutdownEventChannel() noexcept;
bool TryPublishWorldMapDestination(const WorldMapDestination& event) noexcept;

}  // namespace wonderbane::extension
