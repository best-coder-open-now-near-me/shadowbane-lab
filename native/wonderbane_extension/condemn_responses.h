#pragma once
#include "event_channel.h"
#include <Windows.h>
#include <array>
#include <cstdint>
namespace wonderbane::extension::condemn {
using Key = std::array<std::uint32_t, 2>;
constexpr std::size_t kRows = 512, kCapacity = 32;
struct Row { std::uint32_t kind = 0; Key entry{}, character{}, guild{}, nation{}; std::uint32_t flags = 0; };
struct Payload {
    std::uint32_t operation = 0, status = 0, scope = 0, fields = 0;
    Key building{}, entry{}, character{}, guild{}, nation{};
    std::uint32_t state = 0, inverted = 0, reported_count = 0, row_count = 0;
    std::array<Row, kRows> rows{};
};
struct alignas(8) Record {
    volatile LONG64 sequence = 0;
    std::uint64_t tick_ms = 0;
    std::uint32_t thread_id = 0, stage = 0; // decoded=1, processing=2, returned=3
    std::uint64_t decode_sequence = 0, scene_epoch = 0;
    Key local{};
    std::uint32_t flags = 0, caller_rva = 0;
    Payload payload{};
};
struct alignas(8) Storage {
    char magic[8];
    std::uint32_t schema, record_size, capacity, process_id;
    std::uint64_t creation;
    volatile LONG64 sequence, overwritten;
    volatile LONG stopped, rejected;
    volatile LONG64 ticket_drops;
    Record records[kCapacity];
};
static_assert(sizeof(Row) == 40 && sizeof(Payload) == 20552 && sizeof(Record) == 20608);
static_assert(offsetof(Storage, records) == 64 && sizeof(Storage) == 659520);
// Permanent response observation, not command authority. No native message or
// socket pointer is published. Callback call-through stays pinned until exit.
DWORD Start(const ProcessIdentity&) noexcept;
void Stop() noexcept;
}
