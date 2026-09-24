#include "vendor_menu_native.h"
#include "vendor_native.h"
#include "native_hud_order.h"
#include <algorithm>
#include <atomic>
#include <cwchar>
namespace wonderbane::extension::vendor_menu {
namespace {
bool Read(std::uint32_t p, void* out, std::size_t n) noexcept {
    if (p < 0x10000 || p % 4 || !n || n > 8192 || p >= 0x80000000U || n > 0x80000000U - p) { return false; }
    __try { std::memcpy(out, reinterpret_cast<void*>(p), n); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Reader {
    std::uint32_t base; bool ok = true;
    std::uint32_t Word(std::uint32_t p) noexcept { std::uint32_t v = 0; ok = Read(p, &v, 4) && ok; return v; }
    void Require(std::uint32_t p, std::uint32_t v) noexcept { ok = Word(p) == v && ok; }
    template<std::size_t N> std::size_t Vector(std::uint32_t p, std::array<std::uint32_t, N>& out) noexcept {
        const auto begin = Word(p), end = Word(p + 4), cap = Word(p + 8);
        if (!begin && !end && !cap) { return 0; }
        if (!ok || begin < 0x10000 || (begin | end | cap) % 4 || begin > end || end > cap
            || cap >= 0x80000000U || end - begin > N * 4) { ok = false; return 0; }
        const std::size_t count = (end - begin) / 4;
        for (std::size_t i = 0; i < count; ++i) {
            out[i] = Word(begin + static_cast<std::uint32_t>(i * 4));
            if (out[i] < 0x10000 || out[i] % 4 || out[i] >= 0x80000000U
                || std::find(out.begin(), out.begin() + i, out[i]) != out.begin() + i) { ok = false; }
        }
        return count;
    }
    bool Name(std::uint32_t p, const wchar_t* wanted) noexcept {
        const auto begin = Word(p + 0x168), end = Word(p + 0x16c), cap = Word(p + 0x170);
        const auto length = std::wcslen(wanted);
        if (!ok || begin < 0x10000 || (begin | end | cap) % 2 || begin > end || end > cap
            || cap >= 0x80000000U || end - begin > 512 || end - begin != length * 2) { return false; }
        std::array<wchar_t, 256> text{};
        return (!length || Read(begin, text.data(), length * 2)) && std::equal(text.begin(), text.begin() + length, wanted);
    }
    bool Visible(std::uint32_t p) noexcept { return Word(p + 0x1a8) == 0 && (Word(p + 0x304) & 0xff00) == 0 && ok; }
    bool Action(std::uint32_t p, std::uint32_t id) noexcept {
        Require(p + 0x1d0, id); Require(p + 0x1d4, 0); Require(p + 0x1d8, 0);
        // Copying and destroying the native string belongs to the ordinary handler.
        // Restrict admitted configured actions to the observed empty payload.
        const auto begin = Word(p + 0x1e0), end = Word(p + 0x1e4), cap = Word(p + 0x1e8);
        if (begin != end || begin > cap || (begin | cap) % 2 || cap >= 0x80000000U
            || (begin && begin < 0x10000) || (!begin && cap)) { ok = false; }
        return ok;
    }
};
struct Recipe {
    std::uint32_t pages = 0, panel = 0, list = 0, selected = 0, activated = 0;
    std::array<std::uint32_t, 256> nodes{}, rows{}, entries{}, ids{};
    std::size_t node_count = 0, row_count = 0;
};
bool Contains(const Recipe& g, std::uint32_t p) noexcept {
    return std::find(g.nodes.begin(), g.nodes.begin() + g.node_count, p) != g.nodes.begin() + g.node_count;
}
bool RecipeGraph(Reader& r, const wire::Snapshot& s, Recipe& g) noexcept {
    if (!s.recipe) { return false; }
    std::array<std::uint32_t, 512> children{};
    const auto count = r.Vector(s.recipe + 0x54, children);
    for (std::size_t i = 0; i < count; ++i) { r.Require(children[i] + 0x3bc, s.recipe); }
    g.pages = r.Word(s.recipe + 0x518);
    if (std::find(children.begin(), children.begin() + count, g.pages) == children.begin() + count) { return false; }
    r.Require(g.pages, r.base + 0x116b510); r.Require(g.pages + 0x3bc, s.recipe);
    r.Require(g.pages + 0x40c, 0);
    if (!r.Name(g.pages, L"ItemCreationPages")) { return false; }
    std::array<std::uint32_t, 8> tabs{};
    if (!r.Vector(g.pages + 0x400, tabs)) { return false; }
    g.panel = r.Word(tabs[0] + 4);
    r.Require(g.panel, r.base + 0x1169ec0); r.Require(g.panel + 0x3bc, s.recipe);
    if (!r.Visible(g.pages) || !r.Visible(g.panel)) { return false; }
    const auto callback = r.Word(tabs[0] + 0x50);
    r.Require(callback, r.base + 0x116c2c0); r.Require(callback + 4, s.recipe);
    r.Require(callback + 8, r.base + 0x238ad); r.Require(callback + 12, 0);
    g.nodes[g.node_count++] = g.panel;
    std::array<unsigned, 256> depths{};
    for (std::size_t at = 0; r.ok && at < g.node_count; ++at) {
        const auto container = g.nodes[at], cls = r.Word(container);
        if (cls != r.base + 0x1169ec0 && cls != r.base + 0x11657c8) { continue; }
        std::array<std::uint32_t, 256> nested{};
        const auto n = r.Vector(container + 0x40, nested);
        if ((n && depths[at] >= 8) || n > g.nodes.size() - g.node_count) { return false; }
        for (std::size_t i = 0; i < n; ++i) {
            if (Contains(g, nested[i])) { return false; }
            r.Require(nested[i] + 0x3bc, s.recipe);
            depths[g.node_count] = depths[at] + 1; g.nodes[g.node_count++] = nested[i];
        }
    }
    g.list = r.Word(s.recipe + 0x520);
    if (!Contains(g, g.list) || !r.Name(g.list, L"ITEMLIST")) { return false; }
    r.Require(g.list, r.base + 0x116acf0); r.Require(g.list + 0x3bc, s.recipe);
    g.row_count = r.Vector(g.list + 0x408, g.rows);
    g.selected = r.Word(g.list + 0x404); g.activated = r.Word(s.recipe + 0x45c);
    bool selected_found = !g.selected, activated_found = !g.activated;
    for (std::size_t i = 0; r.ok && i < g.row_count; ++i) {
        const auto row = g.rows[i];
        r.Require(row, r.base + 0x116aebc); r.Require(row + 0x3bc, s.recipe); r.Require(row + 0x458, g.list);
        g.entries[i] = r.Word(row + 0x44c); r.Require(g.entries[i], r.base + 0x116c2d0);
        g.ids[i] = r.Word(g.entries[i] + 0x10); r.Require(g.entries[i] + 0x14, 0);
        if (!g.ids[i]) { return false; }
        for (std::size_t j = 0; j < i; ++j) { if (g.ids[i] == g.ids[j] || g.entries[i] == g.entries[j]) { return false; } }
        selected_found |= g.selected == row; activated_found |= g.activated == g.entries[i];
    }
    return r.ok && selected_found && activated_found;
}
bool Route(Reader& r, const wire::Snapshot& s, const Recipe& g, std::uint32_t control) noexcept {
    std::array<std::uint32_t, 16> seen{}; std::size_t count = 0;
    while (r.ok && control != g.pages) {
        if (!control || count == seen.size() || std::find(seen.begin(), seen.begin() + count, control) != seen.begin() + count) { return false; }
        // The leaf may be a strictly qualified clipped row awaiting native scroll.
        // Its own visibility is checked separately; every event ancestor must be usable.
        if (count && !r.Visible(control)) { return false; }
        seen[count++] = control; r.Require(control + 0x3bc, s.recipe);
        const auto cls = r.Word(control);
        const bool row = cls == r.base + 0x116aebc
            && std::find(g.rows.begin(), g.rows.begin() + g.row_count, control) != g.rows.begin() + g.row_count;
        if (!row && (!Contains(g, control) || (cls != r.base + 0x1169ec0
            && cls != r.base + 0x11657c8 && cls != r.base + 0x116acf0))) { return false; }
        // Every admitted intermediate class uses generic event handler 5f57e0.
        control = r.Word(control + 0xe8);
    }
    return r.ok && control == g.pages && r.Visible(g.pages) && r.Visible(g.panel);
}
bool Button(Reader& r, std::uint32_t hud, const wchar_t* name, std::uint32_t action, std::uint32_t& result) noexcept {
    result = 0; std::array<std::uint32_t, 512> children{};
    const auto count = r.Vector(hud + 0x54, children);
    for (std::size_t i = 0; r.ok && i < count; ++i) {
        const auto p = children[i]; r.Require(p + 0x3bc, hud);
        if (r.Word(p) != r.base + 0x1169ec0 || !r.Name(p, name)) { continue; }
        if (result || !r.Visible(p) || !r.Action(p, action) || r.Word(p + 0xe8)) { return false; }
        result = p;
    }
    return r.ok && result;
}
bool Matches(std::uintptr_t base, const movement::NativeScene& scene, const wire::Snapshot& expected) noexcept {
    wire::Snapshot now{};
    if (!Capture(base, scene, now)) { return false; }
    now.revision = expected.revision; return wire::Equal(now, expected);
}
bool CallButton(std::uintptr_t base, std::uint32_t control) noexcept {
    using Fn = bool (__thiscall*)(void*, std::uint32_t, std::uint32_t);
    __try { (void)reinterpret_cast<Fn>(base + 0x5f5440)(reinterpret_cast<void*>(control), 0, 1); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool CallSelect(std::uintptr_t base, std::uint32_t list, std::uint32_t row) noexcept {
    using Fn = void (__thiscall*)(void*, void*);
    __try { reinterpret_cast<Fn>(base + 0x613520)(reinterpret_cast<void*>(list), reinterpret_cast<void*>(row)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool CallActivate(std::uintptr_t base, std::uint32_t row) noexcept {
    using Fn = bool (__thiscall*)(void*, std::uint32_t);
    __try { (void)reinterpret_cast<Fn>(base + 0x61c7f0)(reinterpret_cast<void*>(row), 0); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool CallScroll(std::uintptr_t base, std::uint32_t list, std::uint32_t index) noexcept {
    using Fn = void (__thiscall*)(void*, std::uint32_t);
    __try { reinterpret_cast<Fn>(base + 0x612660)(reinterpret_cast<void*>(list), index); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
std::atomic_flag invoking = ATOMIC_FLAG_INIT;
struct InvokeGuard { ~InvokeGuard() { invoking.clear(std::memory_order_release); } };
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, wire::Snapshot& out) noexcept {
    out = {}; vendor::wire::Snapshot v{}; bool contains = false, top = false;
    if (!vendor::Capture(base, scene, v, 0, contains, top)) { return false; }
    wire::Snapshot s{}; s.scene = v.scene; s.root = v.root; s.manager = v.manager;
    s.menu = v.menu; s.hireling = v.hireling; s.building = v.building; s.vendor = v.vendor;
    s.recipe = v.recipe; s.inventory = v.inventory;
    Reader r{static_cast<std::uint32_t>(base)};
    const auto head = r.Word(s.root + 0x20), tail = r.Word(head + 4);
    auto node = r.Word(head), previous = head;
    std::array<std::uint32_t, 128> nodes{}, huds{}; std::size_t count = 0;
    while (r.ok && node != head) {
        if (count == nodes.size() || std::find(nodes.begin(), nodes.begin() + count, node) != nodes.begin() + count) { return false; }
        r.Require(node + 4, previous); nodes[count] = node;
        const auto hud = r.Word(node + 8);
        if (!hud || std::find(huds.begin(), huds.begin() + count, hud) != huds.begin() + count) { return false; }
        huds[count++] = hud; ObserveActionFront(s.front_hud, base, hud, r.Word(hud));
        previous = node; node = r.Word(node);
    }
    if (!r.ok || previous != tail || !count) { return false; }
    if (s.inventory) {
        // A present HUD does not establish a ready owned list. This does not
        // claim that its entries are fresh or that the inventory is complete.
        const auto listing = r.Word(s.inventory + 0x3f0);
        std::array<std::uint32_t, 512> children{};
        const auto child_count = r.Vector(s.inventory + 0x54, children);
        for (std::size_t i = 0; i < child_count; ++i) { r.Require(children[i] + 0x3bc, s.inventory); }
        if (!listing || std::find(children.begin(), children.begin() + child_count, listing) == children.begin() + child_count) { return false; }
        r.Require(listing, r.base + 0x116acf0); r.Require(listing + 0x3bc, s.inventory);
    }
    if (s.recipe) {
        s.item_template = v.item_template; s.prefix = v.prefix; s.suffix = v.suffix; s.mode = v.mode;
        s.table = v.table; s.quantity = v.quantity; s.multiple = v.multiple;
        s.sentinel = r.Word(s.recipe + 0x400); Recipe g{};
        if (!RecipeGraph(r, s, g)) { return false; }
        s.recipe_list = g.list;
        for (std::size_t i = 0; i < g.row_count; ++i) {
            if (g.rows[i] == g.selected) { s.selected_template = g.ids[i]; }
            if (g.entries[i] == g.activated) { s.activated_template = g.ids[i]; }
        }
        if (s.activated_template != s.item_template) { return false; }
    }
    auto valid = s; valid.revision = 1;
    if (!r.ok || !wire::ValidSnapshot(valid) || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    out = s; return true;
}
wire::Outcome Invoke(std::uintptr_t base, const movement::NativeScene& scene, wire::Verb verb,
    const wire::Command& command, Admission admit, void* context) noexcept {
    using O = wire::Outcome;
    if (invoking.test_and_set(std::memory_order_acquire)) { return O::unavailable; }
    InvokeGuard guard;
    if (!admit || !wire::Valid(verb, command) || verb == wire::Verb::inspect) { return O::invalid; }
    const auto& expected = command.expected;
    if (!admit(context) || !Matches(base, scene, expected)) { return O::stale; }
    if (wire::Reached(verb, command, expected)) { return O::observed; }
    auto current = expected;
    if (verb == wire::Verb::select_recipe) {
        Recipe initial{}; Reader r{static_cast<std::uint32_t>(base)};
        if (!RecipeGraph(r, current, initial)) { return O::unavailable; }
        std::size_t index = 0;
        while (index < initial.row_count && initial.ids[index] != command.item_template) { ++index; }
        if (index == initial.row_count) { return O::unavailable; }
        const auto row = initial.rows[index], list = initial.list, entry = initial.entries[index];
        auto check = [&](bool allow_clipped) noexcept {
            if (!admit(context) || !Matches(base, scene, current)) { return false; }
            Reader q{static_cast<std::uint32_t>(base)}; Recipe g{};
            if (!RecipeGraph(q, current, g) || g.list != list || index >= g.row_count
                || g.rows[index] != row || g.entries[index] != entry || g.ids[index] != command.item_template
                || !Route(q, current, g, row) || !q.Action(row, 0) || q.Word(row + 0x1a8)
                || !q.Visible(list)) { return false; }
            const auto hidden = (q.Word(row + 0x304) >> 8) & 0xff;
            if (hidden) {
                const auto first = q.Word(list + 0x418), page = q.Word(list + 0x414), visible = q.Word(list + 0x41c), height = q.Word(list + 0x420);
                if (!allow_clipped || hidden != 1 || !page || page > g.row_count || !visible || visible > g.row_count
                    || first > g.row_count - page || first > g.row_count - visible || !height || height > 4096
                    || (index >= first && index < first + visible) || q.Word(row + 0x420) != index) { return false; }
            }
            return q.ok;
        };
        if (!check(true)) { return O::stale; }
        bool mutated = false;
        if (r.Word(row + 0x304) & 0xff00) {
            if (!r.ok || !CallScroll(base, list, static_cast<std::uint32_t>(index))) { return O::uncertain; }
            mutated = true;
            if (!check(false)) { return O::uncertain; }
        }
        if (!check(false)) { return mutated ? O::uncertain : O::stale; }
        if (!CallSelect(base, list, row)) { return O::uncertain; }
        current.selected_template = command.item_template;
        if (!check(false)) { return O::uncertain; }
        return CallActivate(base, row) ? O::submitted : O::uncertain;
    }
    auto resolve = [&](std::uint32_t& control) noexcept {
        Reader r{static_cast<std::uint32_t>(base)};
        switch (verb) {
        case wire::Verb::open_recipe: return Button(r, current.menu, L"BTNCREATEITEM", 0x5a1, control);
        case wire::Verb::open_inventory: return Button(r, current.menu, L"BTNVIEW", 0x58c, control);
        case wire::Verb::close_recipe: return Button(r, current.recipe, L"CANCEL", 50, control);
        case wire::Verb::close_inventory: return Button(r, current.inventory, L"CANCEL", 50, control);
        case wire::Verb::random_mode: {
            Recipe g{}; if (!RecipeGraph(r, current, g)) { return false; } control = 0;
            for (std::size_t i = 0; r.ok && i < g.node_count; ++i) {
                const auto p = g.nodes[i];
                if (r.Word(p) != r.base + 0x1169ec0 || !r.Name(p, L"MAGIC")) { continue; }
                if (control || !r.Visible(p) || !r.Action(p, 0x71d) || !Route(r, current, g, p)) { return false; }
                control = p;
            }
            return r.ok && control;
        }
        default: return false;
        }
    };
    std::uint32_t control = 0, checked = 0;
    if (!resolve(control)) { return O::unavailable; }
    if (!admit(context) || !Matches(base, scene, current) || !resolve(checked) || checked != control) { return O::stale; }
    return CallButton(base, control) ? O::submitted : O::uncertain;
}
}
