#include "guard_funding_native.h"
#include <algorithm>
#include <array>
namespace wonderbane::extension::guard_funding {
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
    void Require(std::uintptr_t p, std::uint32_t value) noexcept { ok = Word(p) == value && ok; }
    wire::Key Key(std::uintptr_t p) noexcept { return {Word(p), Word(p + 4)}; }
    template<std::size_t N> std::size_t Vector(std::uintptr_t p, std::array<std::uint32_t, N>& out) noexcept {
        const auto begin = Word(p), end = Word(p + 4), cap = Word(p + 8);
        if (!begin && !end && !cap) { return 0; }
        if (begin < 0x10000 || (begin | end | cap) % 4 || begin > end || end > cap
            || cap >= 0x80000000 || (end - begin) / 4 > N) { ok = false; return 0; }
        const auto count = (end - begin) / 4;
        for (std::size_t i = 0; i < count; ++i) {
            out[i] = Word(begin + 4 * i);
            if (!out[i]) { ok = false; }
            for (std::size_t j = 0; j < i; ++j) { if (out[i] == out[j]) { ok = false; } }
        }
        return count;
    }
    std::size_t Text(std::uintptr_t p, std::array<wchar_t, 512>& text) noexcept {
        const auto begin = Word(p + 4), end = Word(p + 8), cap = Word(p + 12);
        if (!begin && !end && !cap) { return 0; }
        if (begin < 0x10000 || begin % 4 || (end | cap) % 2 || begin > end || end > cap
            || cap >= 0x80000000 || end - begin > 1024) { ok = false; return 0; }
        if (end > begin && !Read(begin, text.data(), end - begin)) { ok = false; return 0; }
        return (end - begin) / 2;
    }
    bool Name(std::uintptr_t p, const wchar_t* wanted, std::size_t count) noexcept {
        std::array<wchar_t, 512> text{};
        return Text(p, text) == count && !std::memcmp(text.data(), wanted, count * 2);
    }
};
bool Purse(std::uintptr_t base, const movement::NativeScene& scene, std::uint32_t& amount) noexcept {
    Reader r;
    r.Require(base + 0x16a2d98, static_cast<std::uint32_t>(scene.actor));
    if (r.Key(scene.actor + 0x18) != scene.identity) { return false; }
    r.Require(scene.actor + 0x688, static_cast<std::uint32_t>(base + 0x11415e4));
    r.Require(base + 0x11415e4, static_cast<std::uint32_t>(base + 0x1686f));
    r.Require(base + 0x11415e8, static_cast<std::uint32_t>(base + 0x1c49f));
    if (!r.ok || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    __try {
        using Getter = std::uint32_t (__thiscall*)(void*);
        amount = reinterpret_cast<Getter>(base + 0x4bc10)(reinterpret_cast<void*>(scene.actor + 0x688));
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
    return amount <= INT32_MAX && movement::NativeMovementLifetimeCurrent(scene);
}
bool Reserve(Reader& r, std::uintptr_t p, std::uint32_t wanted, std::uint32_t& minimum) noexcept {
    const auto header = r.Word(p), count = r.Word(p + 4);
    const auto root = r.Word(header + 4), first = r.Word(header + 8), last = r.Word(header + 12);
    minimum = 0;
    if (count > 1024) { return false; }
    if (!count) { return r.ok && !root && first == header && last == header; }
    std::array<std::uint32_t, 1024> seen{}, resources{}, pending{}, parents{};
    std::size_t next = 1, found = 0;
    pending[0] = root; parents[0] = header;
    while (next && r.ok) {
        --next; const auto node = pending[next], parent = parents[next];
        if (!node || node == header || found >= count) { return false; }
        const auto resource = r.Word(node + 0x10), reserve = r.Word(node + 0x14);
        for (std::size_t i = 0; i < found; ++i) {
            if (seen[i] == node || resources[i] == resource) { return false; }
        }
        seen[found] = node; resources[found++] = resource;
        r.Require(node + 4, parent);
        if (!resource || reserve > INT32_MAX) { return false; }
        if (resource == wanted) { minimum = reserve; }
        for (const auto offset : {8U, 12U}) {
            if (const auto child = r.Word(node + offset)) {
                if (next >= count) { return false; }
                pending[next] = child; parents[next++] = node;
            }
        }
    }
    if (found != count) { return false; }
    auto low = root, high = root;
    for (std::size_t i = 0; i < count && r.Word(low + 8); ++i) { low = r.Word(low + 8); }
    for (std::size_t i = 0; i < count && r.Word(high + 12); ++i) { high = r.Word(high + 12); }
    return r.ok && low == first && high == last;
}
bool Warehouse(Reader& r, std::uintptr_t base, wire::Snapshot& s) noexcept {
    s.manager = s.hud; s.source_object = r.Word(s.hud + 0x378);
    r.Require(s.source_object, static_cast<std::uint32_t>(base + 0x114165c));
    s.source = r.Key(s.source_object + 0x18); s.quote = r.Word(s.hud + 0x10c);
    std::array<std::uint32_t, 512> children{}; const auto count = r.Vector(s.hud + 0x54, children);
    std::uint32_t list = 0;
    for (std::size_t i = 0; r.ok && i < count; ++i) {
        const auto child = children[i]; r.Require(child + 0x3bc, s.hud);
        if (!r.Name(child + 0x164, L"WAREHOUSE_INV", 13)) { continue; }
        if (list) { return false; } list = child;
        r.Require(list, static_cast<std::uint32_t>(base + 0x116acf0));
        std::array<std::uint32_t, 1024> rows{}, entries{}, keys{};
        const auto rows_count = r.Vector(list + 0x408, rows);
        for (std::size_t j = 0; r.ok && j < rows_count; ++j) {
            const auto control = rows[j];
            r.Require(control, static_cast<std::uint32_t>(base + 0x116aebc));
            r.Require(control + 0x3bc, s.hud); r.Require(control + 0x458, list);
            const auto entry = r.Word(control + 0x44c), key = r.Word(entry + 0x20);
            r.Require(entry, static_cast<std::uint32_t>(base + 0x116f258));
            const auto balance = r.Word(entry + 0x48);
            if (!key || balance > INT32_MAX) { return false; }
            for (std::size_t k = 0; k < j; ++k) { if (entries[k] == entry || keys[k] == key) { return false; } }
            entries[j] = entry; keys[j] = key;
            if (r.Name(entry + 0x30, L"Gold", 4)) {
                if (s.resource) { return false; }
                s.resource = key; s.balance = balance;
            }
        }
    }
    return r.ok && list && s.resource && Reserve(r, s.hud + 0x3e8, s.resource, s.reserve);
}
bool Quote(Reader& r, std::uintptr_t base, wire::Snapshot& s) noexcept {
    r.Require(s.quote, static_cast<std::uint32_t>(base + 0x1168044));
    r.Require(s.quote + (s.direction == 1 ? 0x108 : 0x104), s.manager);
    if (s.direction == 1) { r.Require(s.quote + 0x388, s.resource); }
    s.limit = r.Word(s.quote + 0x3c0);
    std::array<std::uint32_t, 32> controls{}; const auto count = r.Vector(s.quote + 0x54, controls);
    for (std::size_t i = 0; r.ok && i < count; ++i) {
        const auto control = controls[i]; r.Require(control + 0x3bc, s.quote);
        const bool accept = r.Name(control + 0x164, L"ACCEPT", 6);
        const bool cancel = r.Name(control + 0x164, L"CANCEL", 6);
        const bool helper = r.Name(control + 0x164, L"SLIDEHELPER", 11);
        if (!accept && !cancel && !helper) { continue; }
        auto& target = accept ? s.accept : (cancel ? s.cancel : s.helper);
        if (target) { return false; } target = control;
        r.Require(control, static_cast<std::uint32_t>(base + 0x1169ec0));
        r.Require(control + 0x1a8, 0);
        if ((r.Word(control + 0x304) >> 8) & 0xff) { return false; }
        if (!helper) {
            if (s.direction == 1) {
                r.Require(control + 0x1d0, accept ? 0x1009 : 0x100b);
                r.Require(control + 0x1d4, 0); r.Require(control + 0x1d8, 0);
            } else {
                for (const auto offset : {0x1d4U, 0x1f8U, 0x21cU}) { r.Require(control + offset, 13); }
            }
        }
    }
    if (!r.ok || !s.helper || !s.accept || !s.cancel) { return false; }
    std::array<wchar_t, 512> text{}; const auto length = r.Text(s.helper + 0xa4, text);
    if (!length || length > 10) { return false; }
    std::uint64_t amount = 0;
    for (std::size_t i = 0; i < length; ++i) {
        if (text[i] < L'0' || text[i] > L'9') { return false; }
        amount = amount * 10 + text[i] - L'0';
    }
    if (amount > INT32_MAX) { return false; }
    s.entered = static_cast<std::uint32_t>(amount); return r.ok;
}
bool SetAmount(std::uintptr_t base, std::uint32_t quote, std::uint32_t amount) noexcept {
    __try {
        using Setter = void (__thiscall*)(void*, std::uint32_t);
        reinterpret_cast<Setter>(base + 0x595720)(reinterpret_cast<void*>(quote), amount); return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Confirm(std::uintptr_t base, const wire::Snapshot& s) noexcept {
    __try {
        if (s.direction == 1) {
            using Click = bool (__thiscall*)(void*, std::uint32_t, std::uint32_t);
            (void)reinterpret_cast<Click>(base + 0x5f5440)(reinterpret_cast<void*>(s.accept), 0, 0);
        } else {
            using Deposit = void (__thiscall*)(void*, std::uint32_t);
            reinterpret_cast<Deposit>(base + 0x6cc3e0)(reinterpret_cast<void*>(s.manager), 13);
        }
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, std::uint32_t direction,
    wire::Snapshot& out, bool& top) noexcept {
    out = {}; top = false;
    if (!base || base > UINT32_MAX || !wire::DirectionValid(direction)
        || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    Reader r; wire::Snapshot s{};
    s.scene = scene.epoch; s.revision = 1; s.root = r.Word(base + 0x16a7bfc);
    s.actor = static_cast<std::uint32_t>(scene.actor); s.character = scene.identity; s.direction = direction;
    if (s.root != scene.window) { return false; }
    r.Require(s.root, static_cast<std::uint32_t>(base + 0x1174884)); r.Require(s.root + 0x64, 2);
    if (!r.ok || !Purse(base, scene, s.purse)) { return false; }
    const auto head = r.Word(s.root + 0x20), tail = r.Word(head + 4);
    auto node = r.Word(head), previous = head;
    std::array<std::uint32_t, 128> nodes{}, huds{}; std::size_t count = 0;
    while (r.ok && node != head) {
        if (count == nodes.size()) { return false; }
        const auto hud = r.Word(node + 8);
        if (!hud) { return false; }
        for (std::size_t i = 0; i < count; ++i) { if (nodes[i] == node || huds[i] == hud) { return false; } }
        nodes[count] = node; huds[count++] = hud;
        r.Require(node + 4, previous); previous = node; node = r.Word(node);
        if (direction == 1 && r.Word(hud) == base + 0x1170308) {
            if (s.hud) { return false; } s.hud = hud;
        }
    }
    if (!r.ok || previous != tail) { return false; }
    if (direction == 1) {
        if (!s.hud || !Warehouse(r, base, s)) { return false; }
    } else {
        s.manager = r.Word(s.root + 0xa4);
        r.Require(s.manager, static_cast<std::uint32_t>(base + 0x1171adc));
        r.Require(s.manager + 0xd8, 0); r.Require(s.manager + 0x48, 1);
        s.source = r.Key(s.manager + 0xf0);
        if (s.source != r.Key(s.manager + 0xf8)) { return false; }
        s.hud = r.Word(s.manager + 0x68); s.quote = r.Word(s.manager + 0x74);
        if (s.quote) { r.Require(s.manager + 0xd0, 13); }
        else if (r.Word(s.manager + 0xd0) != 0 && r.Word(s.manager + 0xd0) != 6) { return false; }
        r.Require(s.hud, static_cast<std::uint32_t>(base + 0x116a058)); r.Require(s.hud + 0x104, s.manager);
        s.balance = r.Word(s.manager + 0x1cc);
    }
    const auto active = [&](std::uint32_t hud) { return std::find(huds.begin(), huds.begin() + count, hud) != huds.begin() + count; };
    if (!active(s.hud) || (s.quote && (!active(s.quote) || !Quote(r, base, s)))) { return false; }
    if (!r.ok || !wire::ValidSnapshot(s) || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    top = count && huds[0] == s.quote;
    s.revision = 0; out = s; return true;
}
bool Invoke(std::uintptr_t base, const movement::NativeScene& scene, const wire::Command& c,
    Admission admit, void* context) noexcept {
    if (!wire::Valid(wire::Verb::transfer, c) || !admit || !admit(context)) { return false; }
    wire::Snapshot fresh{}; bool top = false;
    if (!Capture(base, scene, c.direction, fresh, top) || !top) { return false; }
    fresh.revision = c.expected.revision;
    if (!wire::Equal(fresh, c.expected) || !SetAmount(base, fresh.quote, c.amount)) { return false; }
    if (!Capture(base, scene, c.direction, fresh, top) || !top) { return false; }
    fresh.revision = c.expected.revision;
    auto expected = c.expected; expected.entered = c.amount;
    if (!wire::Equal(fresh, expected) || !admit(context) || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    return Confirm(base, fresh);
}
}
