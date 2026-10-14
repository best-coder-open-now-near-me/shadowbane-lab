#pragma once
#include "event_channel.h"
#include <Windows.h>
#include <array>
#include <cstdint>
namespace wonderbane::extension::vendor_production {
using Key = std::array<std::uint32_t, 2>;
constexpr std::size_t kCapacity = 256;
struct Payload {
    std::uint32_t action = 0, error = 0, fields = 0;
    Key building{}, vendor{}, reference{};
    std::uint32_t quantity = 0, marker = 0, prefix = 0, suffix = 0;
    Key item{};
    // The displayed count is an item stack, not the outstanding roll quota.
    std::uint32_t item_template = 0, stack_count = 0, value = 0, seconds = 0,
        duration = 0, queue_ignored = 0, complete = 0;
    Key deposited_item{}, deposited_template{};
    std::uint32_t strongbox_gold = 0, multiple = 0;
    // Preserve rejected observations for diagnosis without granting authority.
    std::uint32_t template_type = 0, queue_flags_raw = 0, rejection = 0, reserved = 0;
    // The same packet also carries a typed-reference vector (including action 13).
    // Copy it while the callback owns the message; never retain native pointers.
    std::uint32_t references_count = 0, references_reserved = 0;
    std::array<Key, 256> references{};
};
struct alignas(8) Record {
    volatile LONG64 sequence = 0;
    std::uint64_t tick_ms = 0;
    std::uint32_t thread_id = 0, stage = 0;
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
static_assert(sizeof(Payload) == 2184 && sizeof(Record) == 2240);
static_assert(offsetof(Storage, records) == 64 && sizeof(Storage) == 573504);
struct Cursor {
    std::uint32_t process_id = 0;
    std::uint64_t creation = 0, sequence = 0, rejected = 0, ticket_drops = 0;
    bool operator==(const Cursor&) const = default;
};
struct Batch {
    Cursor after{};
    std::uint32_t count = 0;
    std::array<Record, kCapacity> records{};
};
// Permanent copied send/receive evidence; never dispatch or request authority.
// Missing lineage, overflow or lost tickets cannot prove a completed order.
bool ReadCursor(Cursor&) noexcept;
bool ReadAfter(const Cursor&, Batch&) noexcept;
DWORD Start(const ProcessIdentity&) noexcept;
void Stop() noexcept;
}
