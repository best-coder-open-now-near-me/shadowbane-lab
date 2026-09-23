#include "condemn_native.h"
#include "native_hud_order.h"
#include <algorithm>
#include <cstring>
namespace wonderbane::extension::condemn::native {
namespace {
bool Read(std::uintptr_t p, void* out, std::size_t size) noexcept {
    if (p < 0x10000 || p % 4 || !size || size > 8192 || p > 0x7fff0000 - size) { return false; }
    __try { std::memcpy(out, reinterpret_cast<void*>(p), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Reader {
    bool ok = true;
    std::uint32_t Word(std::uintptr_t p) noexcept {
        std::uint32_t value = 0; ok = Read(p, &value, 4) && ok; return value;
    }
    void Require(std::uintptr_t p, std::uint32_t v) noexcept { ok = Word(p) == v && ok; }
    Key Identity(std::uintptr_t p) noexcept { return {Word(p), Word(p + 4)}; }
    template<std::size_t N> std::size_t Vector(std::uintptr_t p, std::array<std::uint32_t, N>& out) noexcept {
        const auto begin = Word(p), end = Word(p + 4), cap = Word(p + 8);
        if (!begin && !end && !cap) { return 0; }
        if (begin < 0x10000 || cap >= 0x80000000 || (begin | end | cap) % 4
            || begin > end || end > cap || (end - begin) / 4 > N) { ok = false; return 0; }
        const auto count = (end - begin) / 4;
        for (std::size_t i = 0; i < count; ++i) {
            out[i] = Word(begin + 4 * i);
            if (!out[i] || std::find(out.begin(), out.begin() + i, out[i]) != out.begin() + i) { ok = false; }
        }
        return count;
    }
    bool Name(std::uintptr_t control, const wchar_t* name, std::size_t length) noexcept {
        const auto begin = Word(control + 0x168), end = Word(control + 0x16c), cap = Word(control + 0x170);
        if (!begin && !end && !cap) { return false; }
        if (begin < 0x10000 || begin % 4 || (end | cap) % 2 || begin > end || end > cap
            || cap >= 0x80000000 || end - begin > 1024) { ok = false; return false; }
        if (end - begin != length * 2) { return false; }
        std::array<wchar_t, 16> text{};
        if (length > text.size() || !Read(begin, text.data(), length * 2)) { ok = false; return false; }
        return !std::memcmp(text.data(), name, length * 2);
    }
};
bool Typed(Key k, std::uint32_t type) noexcept { return k[0] && k[1] == type; }
bool HudStack(Reader& r, std::uintptr_t base, Snapshot& s) noexcept {
    const auto head = r.Word(s.root + 0x20), tail = r.Word(head + 4);
    auto node = r.Word(head), previous = head;
    std::array<std::uint32_t, 128> nodes{}, huds{};
    std::size_t count = 0; bool building = false;
    while (r.ok && node != head) {
        if (count == nodes.size()) { return false; }
        const auto hud = r.Word(node + 8), table = r.Word(hud);
        for (std::size_t i = 0; i < count; ++i) {
            if (nodes[i] == node || huds[i] == hud) { return false; }
        }
        nodes[count] = node; huds[count++] = hud;
        r.Require(node + 4, previous);
        ObserveActionFront(s.front, base, hud, table);
        building |= hud == s.building_hud;
        if (table == base + 0x1168e94) {
            if (s.kos) { return false; }
            s.kos = hud;
            r.Require(hud + 0xdc, 0x39);
            // Selected-row refresh calls this exact KOS virtual method.
            r.Require(base + 0x1168e94 + 0x12c, static_cast<std::uint32_t>(base + 0x3b5c));
            if ((r.Word(hud + 0x270) >> 8) & 255) { return false; }
        }
        previous = node; node = r.Word(node);
    }
    return r.ok && previous == tail && building;
}
bool Rows(Reader& r, std::uintptr_t base, const Target& t, Snapshot& s) noexcept {
    std::array<std::uint32_t, 512> children{}, controls{}, entries{};
    std::array<Key, 512> keys{};
    const auto child_count = r.Vector(s.kos + 0x54, children);
    s.list = r.Word(s.kos + 0x3c8); s.selected = r.Word(s.kos + 0x3b8);
    if (std::find(children.begin(), children.begin() + child_count, s.list) == children.begin() + child_count) { return false; }
    r.Require(s.list, static_cast<std::uint32_t>(base + 0x116acf0)); r.Require(s.list + 0x3bc, s.kos);
    s.list_selected = r.Word(s.list + 0x404);
    s.count = static_cast<std::uint32_t>(r.Vector(s.list + 0x408, controls));
    bool selected = !s.selected, list_selected = !s.list_selected;
    for (std::size_t i = 0; r.ok && i < s.count; ++i) {
        const auto control = controls[i], entry = r.Word(control + 0x44c);
        r.Require(control, static_cast<std::uint32_t>(base + 0x116aebc));
        r.Require(control + 0x3bc, s.kos); r.Require(control + 0x458, s.list);
        r.Require(entry, static_cast<std::uint32_t>(base + 0x11693ec)); r.Require(entry + 8, 0x1d);
        const auto row_key = r.Identity(entry + 0x10);
        if (!row_key[0] || !row_key[1]) { return false; }
        for (std::size_t j = 0; j < i; ++j) {
            if (entries[j] == entry || keys[j] == row_key) { return false; }
        }
        entries[i] = entry; keys[i] = row_key;
        selected |= s.selected == entry; list_selected |= s.list_selected == control;
        const std::array<Key, 3> identities{r.Identity(entry + 0x68), r.Identity(entry + 0x70), r.Identity(entry + 0x78)};
        const auto flags = r.Word(entry + 0x84) & 0xffffff;
        for (unsigned j = 0; j < 3; ++j) {
            if (((flags >> (j * 8)) & 255) > 1) { return false; }
            const auto identity = identities[j];
            if ((identity[0] == 0) != (identity[1] == 0)) { return false; }
        }
        const auto wanted = t.scope == 4 ? 1U : 2U;
        bool matches = identities[wanted] == t.identity;
        for (unsigned j = 0; j < 3; ++j) {
            if (j != wanted && identities[j] != Key{}) { matches = false; }
        }
        if (!matches) {
            s.collision |= row_key == t.identity || identities[wanted] == t.identity;
            continue;
        }
        if (s.entry || !Typed(row_key, 23)) { return false; }
        // The unrelated flags must be clear too; mixed flag state is not this scope.
        if (flags & ~(255U << (wanted * 8))) { return false; }
        s.entry = entry; s.row = control; s.entry_key = row_key;
        s.enabled = (flags >> (wanted * 8)) & 255;
    }
    return r.ok && selected && list_selected;
}
bool Button(Reader& r, std::uintptr_t base, Snapshot& s) noexcept {
    std::array<std::uint32_t, 512> children{};
    const auto count = r.Vector(s.building_hud + 0x54, children);
    for (std::size_t i = 0; r.ok && i < count; ++i) {
        const auto child = children[i]; r.Require(child + 0x3bc, s.building_hud);
        if (!r.Name(child, L"BTNKOS", 6)) { continue; }
        if (s.open_button) { return false; }
        s.open_button = child;
        r.Require(child, static_cast<std::uint32_t>(base + 0x1169ec0));
        r.Require(child + 0x1d0, 0x59d); r.Require(child + 0x1d4, 0);
        r.Require(child + 0x1a8, 0);
        if ((r.Word(child + 0x304) >> 8) & 255) { return false; }
    }
    return r.ok;
}
bool CallOpen(std::uintptr_t base, const Snapshot& s) noexcept {
    __try {
        using Click = bool (__thiscall*)(void*, std::uint32_t, std::uint32_t);
        (void)reinterpret_cast<Click>(base + 0x5f5440)(reinterpret_cast<void*>(s.open_button), 0, 0);
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Select(std::uintptr_t base, const Snapshot& s) noexcept {
    __try {
        using SelectRow = void (__thiscall*)(void*, void*);
        reinterpret_cast<SelectRow>(base + 0x613520)(reinterpret_cast<void*>(s.list), reinterpret_cast<void*>(s.row));
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Selected(std::uintptr_t base, const Snapshot& s) noexcept {
    __try {
        // The client ignores the event argument but still removes it with RET 4.
        using Changed = void (__thiscall*)(void*, std::uint32_t);
        reinterpret_cast<Changed>(base + 0x5b1c40)(reinterpret_cast<void*>(s.kos), 0);
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Assign(std::uintptr_t base, const Snapshot& s, const Target& t) noexcept {
    __try {
        using AssignKey = void* (__thiscall*)(void*, const Key*);
        const Key empty{};
        for (unsigned i = 0; i < 3; ++i) {
            const Key* value = i == (t.scope == 4 ? 1U : 2U) ? &t.identity : &empty;
            reinterpret_cast<AssignKey>(base + 0x111ba0)(reinterpret_cast<void*>(s.kos + 0x3e0 + i * 8), value);
        }
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Send(std::uintptr_t base, const Snapshot& s, const Target& t, Action action) noexcept {
    __try {
        if (action == Action::add) {
            using Add = void (__thiscall*)(void*, std::uint32_t, std::uint32_t);
            reinterpret_cast<Add>(base + 0x5b04e0)(reinterpret_cast<void*>(s.kos), t.scope, 0);
        } else {
            using Enable = void (__thiscall*)(void*);
            reinterpret_cast<Enable>(base + 0x5b1640)(reinterpret_cast<void*>(s.kos));
        }
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
}
bool Valid(const Target& t) noexcept {
    return Typed(t.building, 8) && Typed(t.identity, 23) && (t.scope == 4 || t.scope == 5);
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, const Target& t, Snapshot& out) noexcept {
    out = {};
    if (!base || base > UINT32_MAX || !Valid(t) || !scene.epoch || !Typed(scene.identity, 53)
        || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    Reader r; Snapshot s{}; s.scene = scene.epoch; s.local = scene.identity;
    s.root = r.Word(base + 0x16a7bfc);
    if (s.root != scene.window) { return false; }
    r.Require(s.root, static_cast<std::uint32_t>(base + 0x1174884)); r.Require(s.root + 0x64, 2);
    if (r.Word(s.root + 0x138) & 255) { return false; }
    s.manager = r.Word(s.root + 0xa4); r.Require(s.manager, static_cast<std::uint32_t>(base + 0x1171adc));
    r.Require(s.manager + 0x48, 1); r.Require(s.manager + 0xd8, 0);
    const auto mode = r.Word(s.manager + 0xd0);
    if (mode != 0 && mode != 6) { return false; }
    s.building = r.Identity(s.manager + 0xf0);
    if (s.building != t.building || r.Identity(s.manager + 0xf8) != t.building) { return false; }
    s.building_hud = r.Word(s.manager + 0x68);
    r.Require(s.building_hud, static_cast<std::uint32_t>(base + 0x116a058)); r.Require(s.building_hud + 0x104, s.manager);
    if (!HudStack(r, base, s) || !Button(r, base, s)) { return false; }
    if (s.kos) {
        s.context = r.Identity(s.kos + 0x3d0);
        s.flags = r.Word(s.kos + 0x3f8) & 0xffff;
        for (unsigned i = 0; i < 3; ++i) { s.pending[i] = r.Identity(s.kos + 0x3e0 + 8 * i); }
        if (!Rows(r, base, t, s)) { return false; }
    }
    if (!r.ok || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    out = s; return true;
}
Result Invoke(std::uintptr_t base, const movement::NativeScene& scene, const Target& t,
    Action action, const Snapshot& before, Admission admit, void* context) noexcept {
    Snapshot fresh{};
    if (!admit || !admit(context) || !Capture(base, scene, t, fresh) || fresh != before) { return Result::unavailable; }
    if (action == Action::open) {
        if (!fresh.open_button || fresh.front != fresh.building_hud) { return Result::unavailable; }
        // Admission can observe a changed lease/context. Capture again after it.
        if (!admit(context) || !Capture(base, scene, t, fresh) || fresh != before) { return Result::unavailable; }
        return CallOpen(base, fresh) ? Result::submitted : Result::uncertain;
    }
    if ((action != Action::add && action != Action::enable) || !fresh.kos || fresh.front != fresh.kos
        || fresh.context != t.building || fresh.flags || fresh.collision) { return Result::unavailable; }
    Snapshot expected = before;
    if (action == Action::add) {
        if (fresh.entry || fresh.count >= 512) { return Result::unavailable; }
        if (!Assign(base, fresh, t)) { return Result::uncertain; }
        expected.pending = {}; expected.pending[t.scope == 4 ? 1 : 2] = t.identity;
    } else {
        if (!fresh.entry || fresh.enabled) { return Result::unavailable; }
        if (!Select(base, fresh)) { return Result::uncertain; }
        expected.list_selected = fresh.row;
        if (!admit(context) || !Capture(base, scene, t, fresh) || fresh != expected) { return Result::uncertain; }
        if (!Selected(base, fresh)) { return Result::uncertain; }
        expected.selected = fresh.entry;
    }
    if (!admit(context) || !Capture(base, scene, t, fresh) || fresh != expected
        || !movement::NativeMovementLifetimeCurrent(scene)) { return Result::uncertain; }
    return Send(base, fresh, t, action) ? Result::submitted : Result::uncertain;
}
}
