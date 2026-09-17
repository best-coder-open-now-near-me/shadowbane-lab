#include "native_hud_order.h"
#include "vendor_navigation_native.h"
#include <array>
#include <cstring>
namespace wonderbane::extension::vendor_navigation {
namespace {
bool Read(std::uintptr_t p, void* out, std::size_t size) noexcept {
    if (p < 0x10000 || p % 4 || p > 0x7fff0000 - size || !size || size > 8192) { return false; }
    __try { std::memcpy(out, reinterpret_cast<void*>(p), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Reader {
    bool ok = true;
    std::uint32_t Word(std::uintptr_t p) noexcept {
        std::uint32_t value = 0; ok = Read(p, &value, 4) && ok; return value;
    }
    void Require(std::uintptr_t p, std::uint32_t value) noexcept { ok = Word(p) == value && ok; }
    wire::Key Key(std::uintptr_t p) noexcept { return {Word(p), Word(p + 4)}; }
    template<std::size_t N> std::size_t Vector(std::uintptr_t p, std::array<std::uint32_t, N>& out) noexcept {
        const auto begin = Word(p), end = Word(p + 4), capacity = Word(p + 8);
        if (begin == 0 && end == 0 && capacity == 0) { return 0; }
        if (begin < 0x10000 || capacity >= 0x80000000 || (begin | end | capacity) % 4 || begin > end || end > capacity || (end - begin) / 4 > N) {
            ok = false; return 0;
        }
        const auto count = (end - begin) / 4;
        for (std::size_t i = 0; i < count; ++i) {
            out[i] = Word(begin + i * 4);
            if (!out[i]) { ok = false; }
            for (std::size_t j = 0; j < i; ++j) { if (out[i] == out[j]) { ok = false; } }
        }
        return count;
    }
};
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, wire::Snapshot& out) noexcept {
    out = {};
    if (!base || base > UINT32_MAX || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    Reader r; wire::Snapshot s{}; s.scene = scene.epoch;
    s.root = r.Word(base + 0x16a7bfc); if (s.root != scene.window) { return false; }
    r.Require(s.root, static_cast<std::uint32_t>(base + 0x1174884)); r.Require(s.root + 0x64, 2);
    s.manager = r.Word(s.root + 0xa4); r.Require(s.manager, static_cast<std::uint32_t>(base + 0x1171adc));
    s.mode = r.Word(s.manager + 0xd0);
    s.offline = r.Word(s.manager + 0xd8); s.initialized = r.Word(s.manager + 0x48);
    s.building_hud = r.Word(s.manager + 0x68); s.vendor_hud = r.Word(s.manager + 0x78);
    s.building = r.Key(s.manager + 0xf0);
    s.capacity = r.Word(s.manager + 0x380); s.occupied = r.Word(s.manager + 0x37c);
    s.selected_entry = r.Word(s.manager + 0x384);
    if (s.selected_entry) {
        r.Require(s.selected_entry, static_cast<std::uint32_t>(base + 0x1169518));
        r.Require(s.selected_entry + 8, 9);
        s.vendor = r.Key(s.selected_entry + 0x10);
        const auto populated = (r.Word(s.selected_entry + 0x6c) >> 8) & 0xff;
        // AssetManagement can select a vacancy while loading its roster.
        // Retain its pointer for snapshot equality, but never invent a vendor key.
        if (populated > 1 || (populated ? !wire::Hireling(s.vendor) : s.vendor != wire::Key{})) {
            return false;
        }
    }
    for (const auto hud : {s.building_hud, s.vendor_hud}) {
        if (hud) { r.Require(hud, static_cast<std::uint32_t>(base + 0x116a058)); r.Require(hud + 0x104, s.manager); }
    }
    const auto head = r.Word(s.root + 0x20), tail = r.Word(head + 4);
    auto node = r.Word(head), previous = head;
    std::array<std::uint32_t, 128> seen{}, huds{}; std::size_t count = 0;
    while (r.ok && node != head) {
        if (count == seen.size()) { return false; }
        const auto hud = r.Word(node + 8);
        for (std::size_t i = 0; i < count; ++i) { if (seen[i] == node || huds[i] == hud) { return false; } }
        const auto table = r.Word(hud);
        bool tree_companion = false;
        if (!s.front_hud && table == base + 0x116a058 && hud != s.building_hud
            && s.mode == 6 && s.initialized == 1 && s.building_hud
            && s.building[0] && s.building[1] == 8) {
            // Tree management opens its guild panel above the ordinary hireling
            // roster. It acknowledges the same building, not a different modal.
            // Restrict this to navigation; spending keeps its own front-HUD gate.
            const auto owner = r.Word(hud + 0x104);
            tree_companion = owner && owner == r.Word(s.root + 0x90)
                && r.Word(owner) == base + 0x11727c4
                && r.Word(owner + 0x48) == hud
                && r.Word(owner + 0x5c) == 1
                && r.Key(owner + 0x110) == s.building;
        }
        if (!tree_companion) { ObserveActionFront(s.front_hud, base, hud, table); }
        seen[count] = node; huds[count++] = hud; r.Require(node + 4, previous);
        if (hud && hud == s.building_hud) { s.visible |= 1; }
        if (hud && hud == s.vendor_hud) { s.visible |= 2; }
        if (hud && r.Word(hud) == base + 0x1170308) {
            if (s.warehouse_hud) { return false; }
            s.warehouse_hud = hud; s.warehouse_object = r.Word(hud + 0x378);
            r.Require(s.warehouse_object, static_cast<std::uint32_t>(base + 0x114165c));
            s.warehouse = r.Key(s.warehouse_object + 0x18);
            if (!wire::Typed(s.warehouse, 42)) { return false; }
        }
        previous = node; node = r.Word(node);
    }
    if (s.visible && r.Key(s.manager + 0xf8) != s.building) { return false; }
    if (!r.ok || previous != tail || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    auto checked = s; checked.revision = 1;
    if (!wire::ValidSnapshot(checked)) { return false; }
    out = s; return true;
}
namespace {
bool FindHirelingControl(std::uintptr_t base, const wire::Snapshot& s, wire::Key wanted, std::uint32_t& found) noexcept {
    found = 0;
    if (!wire::ValidSnapshot(s) || !wire::Hireling(wanted) || !wire::OwnsBuilding(s, s.building)) { return false; }
    Reader r; std::array<std::uint32_t, 512> children{};
    const auto child_count = r.Vector(s.building_hud + 0x54, children);
    std::array<wire::Key, 128> keys{}; std::size_t occupied = 0, slots = 0;
    std::uint32_t roster = 0;
    for (std::size_t i = 0; r.ok && i < child_count; ++i) {
        const auto child = children[i]; r.Require(child + 0x3bc, s.building_hud);
        if (r.Word(child) != base + 0x116acf0) { continue; }
        std::array<std::uint32_t, 128> controls{}; const auto count = r.Vector(child + 0x408, controls);
        for (std::size_t j = 0; r.ok && j < count; ++j) {
            const auto control = controls[j];
            r.Require(control, static_cast<std::uint32_t>(base + 0x116aebc));
            r.Require(control + 0x3bc, s.building_hud); r.Require(control + 0x458, child);
            const auto entry = r.Word(control + 0x44c);
            if (!entry || r.Word(entry) != base + 0x1169518) { continue; }
            if (roster && roster != child) { return false; } roster = child;
            if (++slots > 128) { return false; }
            r.Require(entry + 8, 9);
            const auto key = r.Key(entry + 0x10);
            const auto populated = (r.Word(entry + 0x6c) >> 8) & 0xff;
            if (populated > 1 || (!populated && key != wire::Key{})) { return false; }
            if (!populated) { continue; }
            if (!wire::Hireling(key) || occupied == keys.size()) { return false; }
            for (std::size_t k = 0; k < occupied; ++k) { if (keys[k] == key) { return false; } }
            keys[occupied++] = key;
            if (key == wanted) {
                if (found || r.Word(control + 0x1a8) || (r.Word(control + 0x304) & 0xff00)) { return false; }
                found = control;
            }
        }
    }
    return r.ok && found && slots == s.capacity && occupied == s.occupied;
}
bool InvokeHireling(std::uintptr_t base, const wire::Snapshot& s, wire::Key key) noexcept {
    std::uint32_t control = 0;
    if (!FindHirelingControl(base, s, key, control)) { return false; }
    Reader r;
    // Event zero is activation. Event one only selects the row when its action
    // map is empty, so its successful return cannot mean the hireling was opened.
    const auto action = r.Word(control + 0x1d0);
    if ((action && action != 0x4ce) || r.Word(control + 0x1d4) || r.Word(control + 0x1d8)) { return false; }
    const auto list = r.Word(control + 0x458);
    if (!r.ok) { return false; }
    __try {
        // The ordinary list setter only assigns its selected control (+0x404).
        // Recheck owned membership before activating; never use a row index or
        // an action copied from some other menu.
        using Select = void (__thiscall*)(void*, void*);
        reinterpret_cast<Select>(base + 0x613520)(reinterpret_cast<void*>(list), reinterpret_cast<void*>(control));
        std::uint32_t checked = 0;
        if (!FindHirelingControl(base, s, key, checked) || checked != control
            || r.Word(list + 0x404) != control || r.Word(control + 0x1d0) != action
            || r.Word(control + 0x1d4) || r.Word(control + 0x1d8) || !r.ok) { return false; }
        using Activate = bool (__thiscall*)(void*, std::uint32_t);
        return reinterpret_cast<Activate>(base + 0x61c7f0)(reinterpret_cast<void*>(control), 0);
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}

}
bool FindVendorControl(std::uintptr_t base, const wire::Snapshot& s, wire::Key key, std::uint32_t& found) noexcept {
    found = 0;
    return wire::Typed(key, 42) && FindHirelingControl(base, s, key, found);
}
bool FindGuardControl(std::uintptr_t base, const wire::Snapshot& s, wire::Key key, std::uint32_t& found) noexcept {
    found = 0;
    return wire::Typed(key, 37) && FindHirelingControl(base, s, key, found);
}
bool InvokeVendor(std::uintptr_t base, const wire::Snapshot& s, wire::Key key) noexcept {
    return wire::Typed(key, 42) && InvokeHireling(base, s, key);
}
bool InvokeGuard(std::uintptr_t base, const wire::Snapshot& s, wire::Key key) noexcept {
    return wire::Typed(key, 37) && InvokeHireling(base, s, key);
}
}
