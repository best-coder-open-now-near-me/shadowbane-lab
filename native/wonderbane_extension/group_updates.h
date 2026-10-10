#pragma once
#include "event_channel.h"
#include <Windows.h>
#include <array>
#include <cstdint>
namespace wonderbane::extension::group_updates {
using Key=std::array<std::uint32_t,2>;
constexpr std::size_t kCapacity=32;
constexpr std::size_t kRows = 10;
struct Row { Key object{}; std::array<float,3> xyz{}; std::uint32_t reserved=0; };
struct Payload {
    std::array<std::uint32_t,55> group{}; // same native context words as NativeGroupContext.digest
    Key sender{};
    std::uint32_t context_reserved=0;
    std::uint32_t kind=0,row_count=0;
    std::array<Row,kRows> rows{};
};
struct alignas(8) Record {
    volatile LONG64 sequence=0;
    std::uint64_t tick_ms=0;
    std::uint32_t thread_id=0,stage=0;
    std::uint64_t decode_sequence=0,processing_generation=0,scene_epoch=0;
    Key local{};
    std::uint32_t flags=0,caller_rva=0;
    Payload payload{};
};
struct alignas(8) Storage {
    char magic[8];
    std::uint32_t schema,record_size,capacity,process_id;
    std::uint64_t creation;
    volatile LONG64 sequence,overwritten;
    volatile LONG stopped,rejected;
    volatile LONG64 ticket_drops;
    Record records[kCapacity];
};
static_assert(offsetof(Storage,records)==64 && sizeof(Record)==544);
// Read-only receive/Process provenance, not server-session or gameplay authority.
DWORD Start(const ProcessIdentity&) noexcept;
void Stop() noexcept;
}
