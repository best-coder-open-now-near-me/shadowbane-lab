#pragma once
#include "movement_wire.h"
#include <array>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension::vendor::wire {
enum class Verb : std::uint32_t { inspect = 8, create = 9, keep = 10, create_random = 32, inspect_random = 33,
    inspect_orders = 56, create_orders = 61, inspect_recycle = 62, recycle = 63 };
enum class Outcome : std::uint32_t { observed = 0, submitted = 1, stale = 2,
    unavailable = 3, invalid = 4, pending = 5, uncertain = 6, exhausted = 7 };
constexpr std::uint32_t magic = 0x57425631, ready = 1, in_flight = 2, unresolved = 4;
// Additive read-only profile: raw remaining counts occupy the first 16 receipt
// extension bytes in snapshot slot order. Old receipts retain zero padding.
constexpr std::uint32_t orders_magic = 0x57425632;
constexpr std::uint32_t recycle_magic = 0x57425231;
using RemainingCounts = std::array<std::uint32_t, 16>;
#pragma pack(push, 1)
struct Slot { std::uint32_t entry = 0, item = 0, state = 0; };
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    std::uint32_t root = 0, manager = 0, menu = 0, recipe = 0, inventory = 0;
    std::uint32_t hireling = 0, building = 0, vendor = 0, item_template = 0;
    std::uint32_t prefix = 0, suffix = 0, mode = 0, table = 0, quantity = 0, multiple = 0, count = 0;
    std::array<Slot, 16> slots{};
    std::uint8_t reserved[16]{};
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Snapshot expected{};
    std::uint32_t item = 0;
    std::uint8_t reserved[244]{};
};
struct OrderBudget {
    std::uint32_t version = 0, orders = 0, quantity = 0, resource = 0, cost = 0, total = 0;
};
struct RecycleBatch {
    std::array<unsigned char,32> digest{};
    std::uint32_t gold = 0, refund = 0;
    std::array<std::uint32_t,48> items{};
    std::uint8_t reserved[12]{};
};
struct RecycleCompletion {
    std::uint64_t floor = 0, sequence = 0;
    std::uint32_t refund = 0, gold = 0;
};
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::uint32_t outcome = 0, flags = 0;
    Snapshot snapshot{};
    std::uint32_t signature = magic, transition_item = 0;
    std::array<std::uint8_t, 16> transition_request{};
    std::uint8_t reserved[24]{};
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 288 && sizeof(Command) == 576 && sizeof(Receipt) == 384);
static_assert(sizeof(OrderBudget) == 24);
static_assert(sizeof(RecycleBatch) == 244 && sizeof(RecycleCompletion) == 24);
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept {
    return std::memcmp(&a, &b, sizeof(a)) == 0;
}
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    if (!s.scene || !s.revision || !s.root || !s.manager || !s.menu || !s.hireling
        || !s.building || !s.vendor || !s.count || s.count > s.slots.size()
        || !movement::wire::Zero(s.reserved, sizeof(s.reserved))) { return false; }
    for (std::size_t i = 0; i < s.slots.size(); ++i) {
        const auto& a = s.slots[i];
        if (i >= s.count) { if (a.entry || a.item || a.state) { return false; } continue; }
        if (!a.entry || a.state > 2 || ((a.state == 0) != (a.item == 0))) { return false; }
        for (std::size_t j = 0; j < i; ++j) {
            if (s.slots[j].entry == a.entry || (a.item && s.slots[j].item == a.item)) { return false; }
        }
    }
    return true;
}
inline bool RandomScepter(const Snapshot& s) noexcept {
    return s.recipe && s.item_template == 26990 && s.prefix == 3362971591U
        && s.suffix == s.prefix && s.mode == 1 && s.table == 12 && s.quantity == 1 && s.multiple <= 1;
}
inline bool RandomSingle(const Snapshot& s) noexcept {
    return s.recipe && s.item_template && s.table && s.mode == 1 && s.prefix == 3362971591U
        && s.suffix == s.prefix && s.quantity == 1 && s.multiple == 0;
}
inline bool RandomOrder(const Snapshot& s) noexcept {
    return s.recipe && s.item_template && s.table && s.mode == 1 && s.prefix == 3362971591U
        && s.suffix == s.prefix && s.quantity >= 2 && s.quantity <= 10 && s.multiple == 1;
}
inline OrderBudget Budget(const Command& command) noexcept {
    OrderBudget result{}; std::memcpy(&result, command.reserved + 16, sizeof(result)); return result;
}
inline RecycleBatch Recycling(const Command& c) noexcept {
    RecycleBatch batch{};std::memcpy(&batch,c.reserved,sizeof(batch));return batch;
}
inline bool EmptyProduction(const Snapshot& s) noexcept {
    for(const auto& slot:s.slots){if(slot.item || slot.state){return false;}}return true;
}
inline bool IsCreate(Verb verb) noexcept {
    return verb == Verb::create || verb == Verb::create_random || verb == Verb::create_orders;
}
inline bool IsInspect(Verb verb) noexcept {
    return verb == Verb::inspect || verb == Verb::inspect_random || verb == Verb::inspect_orders
        || verb == Verb::inspect_recycle;
}
inline bool IsRecycle(Verb v) noexcept {return v==Verb::recycle || v==Verb::inspect_recycle;}
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())) { return false; }
    if (verb == Verb::create_orders) {
        // The immutable batch UUID scopes active quantity orders. Legacy verbs
        // retain all-zero padding and cannot adopt this new command profile.
        const auto budget = Budget(c);
        if (movement::wire::Zero(c.reserved, 16) || budget.version != 1 || !budget.orders || budget.orders > 16
            || budget.quantity != c.expected.quantity || !budget.resource || !budget.cost || budget.cost > INT32_MAX
            || static_cast<std::uint64_t>(budget.orders) * budget.cost > INT32_MAX
            || budget.total != budget.orders * budget.cost
            || !movement::wire::Zero(c.reserved + 40, sizeof(c.reserved) - 40)) { return false; }
    } else if(verb==Verb::recycle) {
        const auto batch=Recycling(c);
        if(!c.item || c.item>batch.items.size() || !batch.refund || batch.gold>INT32_MAX
            || batch.refund>INT32_MAX-batch.gold || movement::wire::Zero(batch.digest.data(),batch.digest.size())
            || !movement::wire::Zero(batch.reserved,sizeof(batch.reserved))){return false;}
        for(std::size_t i=0;i<batch.items.size();++i) {
            if(i<c.item ? !batch.items[i] || (i && batch.items[i-1]>=batch.items[i]) : batch.items[i]!=0){return false;}
        }
    } else if (!movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (IsInspect(verb)) {
        return !c.item && movement::wire::Zero(&c.expected, sizeof(c.expected));
    }
    return ValidSnapshot(c.expected)
        && ((verb == Verb::create && !c.item && RandomScepter(c.expected))
            || (verb == Verb::create_random && !c.item && RandomSingle(c.expected))
            || (verb == Verb::create_orders && !c.item && RandomOrder(c.expected))
            || (verb == Verb::keep && c.item)
            || (verb == Verb::recycle && c.expected.inventory && EmptyProduction(c.expected)));
}
}
