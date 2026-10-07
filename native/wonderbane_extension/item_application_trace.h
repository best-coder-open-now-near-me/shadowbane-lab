#pragma once
#include "event_channel.h"
#include "movement_lifetime.h"
#include "actor_action_wire.h"
#include <Windows.h>
#include <array>
#include <cstdint>
namespace wonderbane::extension::item_trace {
constexpr std::size_t kCapacity=256;
using Key=std::array<std::uint32_t,2>;
// Flags: copied body=1, current native scene=2, single-use decode lineage=4.
// Lineage concerns one native message object, never a server request identity.
struct alignas(8) Record {
    volatile LONG64 sequence{};std::uint64_t tick_ms{};
    std::uint32_t thread_id{},stage{},kind{},flags{}; // stages decode/process/return/owned-return=1..4; kinds item/power=1/2
    std::uint64_t decode_sequence{},scene_epoch{};Key local{};
    std::uint32_t caller_rva{},native_return{};
    actor::wire::Id request{};actor::wire::Digest command{};
    std::uint32_t outcome{},entry{},local_settlement{},history{};
    std::array<std::uint32_t,11> payload{};std::uint32_t reserved{};
};
struct alignas(8) Storage {
    char magic[8];std::uint32_t schema,record_size,capacity,process_id;
    std::uint64_t creation;volatile LONG64 sequence,overwritten;
    volatile LONG stopped,rejected;volatile LONG64 ticket_drops;
    Record records[kCapacity];
};
static_assert(sizeof(Record)==176 && offsetof(Storage,records)==64);
// Optional observation only. Unsupported/disabled/dropped data is unknown,
// never admission, application settlement or proof of network delivery.
DWORD Start(const ProcessIdentity&) noexcept;
void Stop() noexcept;
void OwnedReturn(const actor::wire::Command&,const movement::NativeScene&,
    actor::wire::Outcome,actor::wire::Entry,actor::wire::LocalSettlement,std::uint32_t history) noexcept;
}
