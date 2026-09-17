#pragma once
#include "vendor_navigation_wire.h"
namespace wonderbane::extension::guard_upgrade::wire {
using Outcome = vendor::wire::Outcome;
enum class Verb : std::uint32_t { inspect = 17, upgrade = 18 };
constexpr std::uint32_t magic = 0x57424731, ready = 1, in_flight = 2, unresolved = 4;
#pragma pack(push, 1)
struct Snapshot {
    vendor_navigation::wire::Snapshot navigation{};
    std::uint32_t rank = 0, cost = 0, funds = 0, upgrading = 0, can_upgrade = 0;
    // control_flags: upgrade visible=1, enabled=2, progress visible=4.
    std::uint32_t control_flags = 0, upgrade_control = 0, progress_control = 0;
};
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::array<std::uint8_t, 16> request{};
    Snapshot expected{};
    std::uint8_t reserved[408]{};
};
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    std::uint32_t outcome = 0, flags = 0;
    Snapshot snapshot{};
    std::array<std::uint8_t, 16> transition_request{};
    std::uint32_t signature = magic;
    std::uint8_t reserved[188]{};
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 128 && sizeof(Command) == 576 && sizeof(Receipt) == 384);
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept { return !std::memcmp(&a, &b, sizeof(a)); }
inline bool ValidSnapshot(const Snapshot& s) noexcept {
    const auto& n = s.navigation;
    return vendor_navigation::wire::ValidSnapshot(n) && !n.offline && n.visible == 3
        && vendor_navigation::wire::Typed(n.vendor, 37) && s.rank && s.rank < UINT32_MAX
        && s.cost <= INT32_MAX && s.funds <= INT32_MAX && s.upgrading <= 1
        && s.can_upgrade <= 1 && s.control_flags <= 7 && s.upgrade_control && s.progress_control
        && s.upgrade_control != s.progress_control;
}
inline bool Eligible(const Snapshot& s) noexcept {
    return ValidSnapshot(s) && !s.upgrading && s.can_upgrade && s.cost
        && s.funds >= s.cost && s.control_flags == 3;
}
inline bool SameOwner(const Snapshot& a, const Snapshot& b) noexcept {
    const auto& x = a.navigation; const auto& y = b.navigation;
    return x.scene == y.scene && x.root == y.root && x.manager == y.manager
        && x.building_hud == y.building_hud && x.vendor_hud == y.vendor_hud
        && x.selected_entry == y.selected_entry && x.building == y.building && x.vendor == y.vendor
        && a.upgrade_control == b.upgrade_control && a.progress_control == b.progress_control;
}
inline bool Valid(Verb verb, const Command& c) noexcept {
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || movement::wire::Zero(c.request.data(), c.request.size())
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))) { return false; }
    if (verb == Verb::inspect) { return movement::wire::Zero(&c.expected, sizeof(c.expected)); }
    return verb == Verb::upgrade && Eligible(c.expected);
}
}
