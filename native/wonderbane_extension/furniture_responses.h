#pragma once
#include "event_channel.h"
#include <Windows.h>
#include <array>
#include <cstddef>
#include <cstdint>
namespace wonderbane::extension::furniture {
using Key = std::array<std::uint32_t, 2>;
constexpr std::size_t kRows = 64, kCapacity = 32;
struct Row {
    Key asset{}, instance{}, auxiliary{};
    std::array<float, 3> position{};
    float rotation = 0;
    std::int32_t floor = 0;
    std::uint32_t word34_raw = 0, flag38_raw = 0, reserved = 0;
};
struct Payload {
    std::uint32_t operation = 0, fields = 0, status = 0, refresh = 0;
    Key building{}, structure{}, deed{};
    std::array<float, 3> position{};
    float rotation = 0;
    std::int32_t floor = 0;
    std::uint32_t reported_scene = 0, scene_count = 0, reported_consumed = 0, consumed_count = 0;
    std::uint32_t reported_secondary = 0, secondary_count = 0;
    std::array<std::uint32_t, 3> reserved{};
    std::array<Row, kRows> scene{}, secondary{};
    std::array<Key, kRows> consumed{};
};
struct alignas(8) Record {
    volatile LONG64 sequence = 0;
    std::uint64_t tick_ms = 0;
    std::uint32_t thread_id = 0, stage = 0; // decoded=1, processing=2, returned=3, serializing=4
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
static_assert(sizeof(Row) == 56 && offsetof(Payload, scene) == 96);
static_assert(sizeof(Payload) == 7776 && sizeof(Record) == 7832);
static_assert(offsetof(Storage, records) == 64 && sizeof(Storage) == 250688);
struct Cursor {
    std::uint32_t process_id = 0;
    std::uint64_t creation = 0, sequence = 0, rejected = 0, ticket_drops = 0;
    bool operator==(const Cursor&) const = default;
};
// Allocate off the owner thread's small stack; no native pointer escapes this copy.
struct Batch {
    Cursor after{};
    std::uint32_t count = 0;
    std::array<Record, kCapacity> records{};
};
bool ReadCursor(Cursor&) noexcept;
bool ReadAfter(const Cursor&, Batch&) noexcept;
// Passive diagnostics only. Serializing is neither sent nor server accepted;
// handler return does not establish placement or persistence. No command authority.
DWORD Start(const ProcessIdentity&) noexcept;
void Stop() noexcept;
}
