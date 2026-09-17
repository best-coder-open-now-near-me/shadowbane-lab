#pragma once
#include "vendor_wire.h"
namespace wonderbane::extension::vendor_navigation::wire {
using Outcome = vendor::wire::Outcome;
using Key = std::array<std::uint32_t, 2>;
enum class Verb : std::uint32_t { inspect = 13, building = 14, vendor = 15, guard = 16, warehouse = 22 };
constexpr std::uint32_t magic = 0x57424e32, ready = 1, in_flight = 2, unresolved = 4;
#pragma pack(push, 1)
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    std::uint32_t root = 0, manager = 0, active_manager = 0, mode = 0;
    std::uint32_t building_hud = 0, vendor_hud = 0, selected_entry = 0, visible = 0;
    Key building{}, vendor{};
    std::uint32_t initialized = 0, capacity = 0, occupied = 0, offline = 0;
    std::uint32_t warehouse_hud = 0, warehouse_object = 0;
    Key warehouse{};
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Snapshot expected{};
    Key building{}, vendor{};
    std::uint8_t reserved[424]{};
};
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::uint32_t outcome = 0, flags = 0;
    Snapshot snapshot{};
    std::array<std::uint8_t, 16> transition_request{};
    std::uint32_t signature = magic;
    std::uint8_t reserved[220]{};
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 96 && sizeof(Command) == 576 && sizeof(Receipt) == 384);
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept { return !std::memcmp(&a, &b, sizeof(a)); }
inline bool Typed(Key key, std::uint32_t type) noexcept { return key[0] && key[1] == type; }
inline bool Hireling(Key key) noexcept { return Typed(key, 42) || Typed(key, 37); }
inline bool Matches(Verb verb, Key key) noexcept {
    return (verb == Verb::vendor && Typed(key, 42)) || (verb == Verb::guard && Typed(key, 37));
}
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    return s.scene && s.revision && s.root && s.manager && s.mode <= 64
        && s.visible <= 3 && s.initialized <= 1 && s.offline <= 1
        && s.occupied <= s.capacity && s.capacity <= 128
        && (s.building == Key{} || Typed(s.building, 8))
        && (s.vendor == Key{} || Hireling(s.vendor))
        && (s.vendor == Key{} || s.selected_entry)
        && (!(s.visible & 1) || (s.building_hud && s.initialized && s.mode == 6 && Typed(s.building, 8)))
        && (!(s.visible & 2) || (s.vendor_hud && s.selected_entry && Hireling(s.vendor) && Typed(s.building, 8)))
        && ((!s.warehouse_hud && !s.warehouse_object && s.warehouse == Key{})
            || (s.warehouse_hud && s.warehouse_object && Typed(s.warehouse, 42)));
}
inline bool Opened(const Snapshot& s, Verb verb, Key building, Key vendor = {}) noexcept {
    // The dispatcher global tracks its last manager, not HUD ownership. Tree
    // of Life's ordinary secondary action 0x515 changes it while this building
    // HUD remains open. Capture validates the rooted manager, HUD backlink and
    // live stack membership; retain the global only for snapshot equality.
    if (verb == Verb::warehouse) {
        return !s.offline && s.building == building && Typed(vendor, 42)
            && s.warehouse_hud && s.warehouse_object && s.warehouse == vendor;
    }
    return !s.offline && s.building == building
        && (verb == Verb::building ? (s.visible & 1) != 0
            : Matches(verb, vendor) && (s.visible & 2) && s.vendor == vendor);
}
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (verb == Verb::inspect) {
        return movement::wire::Zero(&c.expected, sizeof(c.expected)) && c.building == Key{} && c.vendor == Key{};
    }
    if (!ValidSnapshot(c.expected) || c.expected.offline || !Typed(c.building, 8)) { return false; }
    return (verb == Verb::building && c.vendor == Key{})
        || ((Matches(verb, c.vendor) || (verb == Verb::warehouse && Typed(c.vendor, 42)))
            && Opened(c.expected, Verb::building, c.building));
}
}
