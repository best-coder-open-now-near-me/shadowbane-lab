#pragma once
#include "vendor_wire.h"
namespace wonderbane::extension::vendor_navigation::wire {
using Outcome = vendor::wire::Outcome;
using Key = std::array<std::uint32_t, 2>;
enum class Verb : std::uint32_t { inspect = 13, building = 14, vendor = 15 };
constexpr std::uint32_t magic = 0x57424e31, ready = 1, in_flight = 2, unresolved = 4;
#pragma pack(push, 1)
struct Snapshot {
    std::uint64_t scene = 0, revision = 0;
    std::uint32_t root = 0, manager = 0, active_manager = 0, mode = 0;
    std::uint32_t building_hud = 0, vendor_hud = 0, selected_entry = 0, visible = 0;
    Key building{}, vendor{};
    std::uint32_t initialized = 0, capacity = 0, occupied = 0, offline = 0;
    std::uint8_t reserved[16]{};
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
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    return s.scene && s.revision && s.root && s.manager && s.mode <= 64
        && s.visible <= 3 && s.initialized <= 1 && s.offline <= 1
        && s.occupied <= s.capacity && s.capacity <= 128
        && (s.building == Key{} || Typed(s.building, 8))
        && (s.vendor == Key{} || Typed(s.vendor, 42))
        && (s.vendor == Key{} || s.selected_entry)
        && (!(s.visible & 1) || (s.building_hud && s.initialized && s.mode == 6 && Typed(s.building, 8)))
        && (!(s.visible & 2) || (s.vendor_hud && s.selected_entry && Typed(s.vendor, 42) && Typed(s.building, 8)))
        && movement::wire::Zero(s.reserved, sizeof(s.reserved));
}
inline bool Opened(const Snapshot& s, Verb verb, Key building, Key vendor = {}) noexcept {
    // The dispatcher global tracks its last manager, not HUD ownership. Tree
    // of Life's ordinary secondary action 0x515 changes it while this building
    // HUD remains open. Capture validates the rooted manager, HUD backlink and
    // live stack membership; retain the global only for snapshot equality.
    return !s.offline && s.building == building
        && (verb == Verb::building ? (s.visible & 1) != 0
            : verb == Verb::vendor && (s.visible & 2) && s.vendor == vendor);
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
        || (verb == Verb::vendor && Typed(c.vendor, 42)
            && Opened(c.expected, Verb::building, c.building));
}
}
