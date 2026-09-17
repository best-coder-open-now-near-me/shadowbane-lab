#include "guard_upgrade_native.h"
#include "vendor_navigation_native.h"
#include <array>
namespace wonderbane::extension::guard_upgrade {
namespace {
bool Read(std::uintptr_t p, void* out, std::size_t size) noexcept {
    if (p < 0x10000 || p % 4 || !size || size > 8192 || p > 0x7fff0000 - size) { return false; }
    __try { std::memcpy(out, reinterpret_cast<void*>(p), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Reader {
    bool ok = true;
    std::uint32_t Word(std::uintptr_t p) noexcept {
        std::uint32_t v = 0; ok = Read(p, &v, 4) && ok; return v;
    }
    void Require(std::uintptr_t p, std::uint32_t v) noexcept { ok = Word(p) == v && ok; }
    bool Name(std::uintptr_t control, const wchar_t* name, std::size_t length) noexcept {
        const auto begin = Word(control + 0x168), end = Word(control + 0x16c), cap = Word(control + 0x170);
        if (!begin && !end && !cap) { return false; }
        if (begin < 0x10000 || begin % 4 || end % 2 || cap % 2 || begin > end
            || end > cap || cap >= 0x80000000 || end - begin > 1024) { ok = false; return false; }
        if (end - begin != length * 2) { return false; }
        std::array<wchar_t, 32> text{};
        if (length > text.size() || !Read(begin, text.data(), length * 2)) { ok = false; return false; }
        return !std::memcmp(text.data(), name, length * 2);
    }
};
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, wire::Snapshot& out, bool& top) noexcept {
    out = {}; top = false;
    wire::Snapshot s{};
    if (!vendor_navigation::Capture(base, scene, s.navigation)) { return false; }
    auto& n = s.navigation;
    n.revision = 1;
    if (n.visible != 3 || !vendor_navigation::wire::Typed(n.vendor, 37)) { return false; }
    std::uint32_t row = 0;
    if (!vendor_navigation::FindGuardControl(base, n, n.vendor, row)) { return false; }
    Reader r;
    r.Require(n.manager + 0x50, 1);
    if (n.vendor_hud == n.building_hud) { return false; }
    s.rank = r.Word(n.selected_entry + 0x28);
    s.cost = r.Word(n.manager + 0x274); s.funds = r.Word(n.manager + 0x1cc);
    const auto flags = r.Word(n.manager + 0x2ac);
    s.upgrading = flags & 0xff; s.can_upgrade = (flags >> 8) & 0xff;
    const auto begin = r.Word(n.vendor_hud + 0x54), end = r.Word(n.vendor_hud + 0x58);
    const auto cap = r.Word(n.vendor_hud + 0x5c);
    if (begin < 0x10000 || (begin | end | cap) % 4 || begin > end || end > cap
        || cap >= 0x80000000 || end - begin > 512 * 4) { return false; }
    std::array<std::uint32_t, 512> seen{};
    std::uint32_t cost_control = 0;
    for (std::size_t i = 0; r.ok && i < (end - begin) / 4; ++i) {
        const auto control = r.Word(begin + 4 * i);
        for (std::size_t j = 0; j < i; ++j) { if (seen[j] == control) { return false; } }
        seen[i] = control;
        r.Require(control + 0x3bc, n.vendor_hud);
        const bool upgrade = r.Name(control, L"BTNUPGRADE", 10);
        const bool progress = r.Name(control, L"SLIDEUPGRADE", 12);
        const bool cost = r.Name(control, L"BTNUPGRADECOST", 14);
        if (!upgrade && !progress && !cost) { continue; }
        r.Require(control, static_cast<std::uint32_t>(base + 0x1169ec0));
        const auto disabled = r.Word(control + 0x1a8), hidden = (r.Word(control + 0x304) >> 8) & 0xff;
        if (disabled > 1 || hidden > 1) { return false; }
        auto& target = upgrade ? s.upgrade_control : (progress ? s.progress_control : cost_control);
        if (target) { return false; } target = control;
        if (upgrade) {
            r.Require(control + 0x1d0, 0x58b); // Ordinary UpgradeHireling action.
            r.Require(control + 0x1d4, 0);
            s.control_flags |= (!hidden ? 1U : 0U) | (!disabled ? 2U : 0U);
        }
        if (progress && !hidden) { s.control_flags |= 4; }
    }
    top = n.front_hud && n.front_hud == n.vendor_hud;
    if (!r.ok || !cost_control || !wire::ValidSnapshot(s) || !movement::NativeMovementLifetimeCurrent(scene)) {
        top = false; return false;
    }
    s.navigation.revision = 0; out = s; return true;
}
bool Invoke(std::uintptr_t base, const wire::Snapshot& s) noexcept {
    if (!base || !wire::Eligible(s)) { return false; }
    __try {
        // Ordinary mode-20 Yes handler calls this method at 0x6c5e3a.
        // It resolves the selected hireling and displayed building itself.
        using Upgrade = void (__thiscall*)(void*);
        reinterpret_cast<Upgrade>(base + 0x6d7c70)(reinterpret_cast<void*>(s.navigation.manager));
        return true; // Submission only; controller requires the response and gold debit.
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
}
