#pragma once
#include "event_channel.h"
#include <Windows.h>
#include <array>
#include <cstdint>
namespace wonderbane::extension::group_messages {
using Key=std::array<std::uint32_t,2>;
constexpr std::size_t kCapacity=32;
constexpr std::size_t kNameUnits = 96, kTextUnits = 128;
struct Payload {
    std::array<std::uint32_t,55> group{}; // same native context words as NativeGroupContext.digest
    Key sender_key{};
    std::uint32_t context_reserved=0;
    std::uint32_t channel = 0, sender_units = 0, text_units = 0, reserved = 0;
    std::array<std::uint16_t, kNameUnits> sender{};
    std::array<std::uint16_t, kTextUnits> text{};
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
static_assert(offsetof(Storage,records)==64 && sizeof(Record)==760);
// Read-only receive/Process provenance, not server-session or gameplay authority.
DWORD Start(const ProcessIdentity&) noexcept;
void Stop() noexcept;
}
