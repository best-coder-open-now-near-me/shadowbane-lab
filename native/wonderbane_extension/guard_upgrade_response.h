#pragma once
#include "guard_upgrade_wire.h"
namespace wonderbane::extension::guard_upgrade {
// Internal observation of the server's replacement building roster. Not wire data.
struct ReturnSnapshot {
    vendor_navigation::wire::Snapshot navigation{};
    vendor_navigation::wire::Key guard{};
    std::uint32_t rank = 0, funds = 0;
};
// A server response can rebuild the building page and its child controls while
// retaining the selected guard page. Admit only the completed response, never a
// new owner to wait on: exact debit and progress/rank must already be present.
inline bool ConfirmedRebuiltGuardPage(const wire::Snapshot& before,
    const wire::Snapshot& after) noexcept {
    const auto& a = before.navigation; const auto& b = after.navigation;
    return wire::Eligible(before) && wire::ValidSnapshot(after)
        && wire::SameGuard(before, after)
        && a.front_hud == a.vendor_hud && b.front_hud == b.vendor_hud
        && a.vendor_hud == b.vendor_hud && a.selected_entry == b.selected_entry
        && a.building_hud != b.building_hud && b.mode == 6
        && after.cost == before.cost && after.funds == before.funds - before.cost
        && ((after.rank == before.rank && after.upgrading && (after.control_flags & 4))
            || after.rank == before.rank + 1);
}
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
