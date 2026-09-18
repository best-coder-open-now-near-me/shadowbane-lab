#pragma once
#include "guard_upgrade_wire.h"
namespace wonderbane::extension::guard_upgrade {
// Internal observation of the server's replacement building roster. Not wire data.
struct ReturnSnapshot {
    vendor_navigation::wire::Snapshot navigation{};
    vendor_navigation::wire::Key guard{};
    std::uint32_t rank = 0, funds = 0;
};
inline bool CanReopen(const wire::Snapshot& before, const ReturnSnapshot& returned) noexcept {
    const auto& a = before.navigation; const auto& b = returned.navigation;
    return wire::Eligible(before) && vendor_navigation::wire::ValidSnapshot(b)
        && !b.offline && b.visible == 1 && !b.vendor_hud && b.front_hud == b.building_hud
        && a.scene == b.scene && a.root == b.root && a.manager == b.manager
        && a.building == b.building && returned.guard == a.vendor
        && returned.funds == before.funds - before.cost
        && (returned.rank == before.rank || returned.rank == before.rank + 1);
}
}
