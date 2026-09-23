#pragma once
#include "movement_wire.h"
#include <array>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension::vendor::wire {
enum class Verb : std::uint32_t { inspect = 8, create = 9, keep = 10 };
enum class Outcome : std::uint32_t { observed = 0, submitted = 1, stale = 2,
    unavailable = 3, invalid = 4, pending = 5, uncertain = 6, exhausted = 7 };
constexpr std::uint32_t magic = 0x57425631, ready = 1, in_flight = 2, unresolved = 4;
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
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (verb == Verb::inspect) {
        return !c.item && movement::wire::Zero(&c.expected, sizeof(c.expected));
    }
    return ValidSnapshot(c.expected)
        && ((verb == Verb::create && !c.item && RandomScepter(c.expected))
            || (verb == Verb::keep && c.item));
}
}
