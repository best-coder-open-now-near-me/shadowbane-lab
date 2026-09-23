#include "native_hud_order.h"
#include "vendor_native.h"
#include <algorithm>
#include <array>
#include <cstring>
namespace wonderbane::extension::vendor {
namespace {
bool Block(std::uint32_t address, void* out, std::size_t count) noexcept {
    if (address < 0x10000 || address % 4 || count > 8192 || address >= 0x80000000U
        || count > 0x80000000U - address) { return false; }
    __try { std::memcpy(out, reinterpret_cast<void*>(address), count); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Reader {
    std::uint32_t base;
    bool ok = true;
    std::uint32_t Word(std::uint32_t p) noexcept {
        std::uint32_t value = 0; ok = Block(p, &value, 4) && ok; return value;
    }
    void Require(std::uint32_t p, std::uint32_t expected) noexcept { ok = Word(p) == expected && ok; }
    template<std::size_t N> std::size_t Vector(std::uint32_t p, std::array<std::uint32_t, N>& out) noexcept {
        const auto begin = Word(p), end = Word(p + 4), capacity = Word(p + 8);
        if (!begin && !end && !capacity) { return 0; }
        if (!ok || begin < 0x10000 || begin % 4 || end % 4 || capacity % 4
            || begin > end || end > capacity || capacity >= 0x80000000U || end - begin > N * 4) {
            ok = false; return 0;
        }
        const std::size_t count = (end - begin) / 4;
        if (count && !Block(begin, out.data(), count * 4)) { ok = false; return 0; }
        for (std::size_t i = 0; i < count; ++i) {
            for (std::size_t j = 0; j < i; ++j) { if (out[i] == out[j]) { ok = false; } }
        }
        return count;
    }
};
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, wire::Snapshot& out,
    std::uint32_t find_item, bool& inventory_contains, bool& top_menu) noexcept {
    out = {}; inventory_contains = top_menu = false;
    if (!base || base > UINT32_MAX || !scene.epoch || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    Reader r{static_cast<std::uint32_t>(base)};
    wire::Snapshot s{}; s.scene = scene.epoch;
    s.root = r.Word(r.base + 0x16A7BFC);
    if (s.root != scene.window) { return false; }
    r.Require(s.root, r.base + 0x1174884); r.Require(s.root + 0x64, 2);
    s.manager = r.Word(s.root + 0xA4); r.Require(s.manager, r.base + 0x1171ADC);
    s.menu = r.Word(s.manager + 0x78); r.Require(s.menu, r.base + 0x116A058);
    r.Require(s.menu + 0x104, s.manager); r.Require(s.manager + 0xD8, 0);
    s.building = r.Word(s.manager + 0xF0); r.Require(s.manager + 0xF4, 8);
    r.Require(s.manager + 0xF8, s.building); r.Require(s.manager + 0xFC, 8);
    s.hireling = r.Word(s.manager + 0x384); r.Require(s.hireling, r.base + 0x1169518);
    s.vendor = r.Word(s.hireling + 0x10); r.Require(s.hireling + 0x14, 42);
    std::array<std::uint32_t, 128> huds{}, nodes{};
    std::size_t hud_count = 0;
    std::uint32_t front = 0;
    const auto head = r.Word(s.root + 0x20), tail = r.Word(head + 4);
    auto node = r.Word(head), previous = head;
    while (r.ok && node != head) {
        if (hud_count == huds.size()) { return false; }
        for (std::size_t i = 0; i < hud_count; ++i) { if (nodes[i] == node) { return false; } }
        r.Require(node + 4, previous); nodes[hud_count] = node;
        const auto hud = r.Word(node + 8);
        ObserveActionFront(front, base, hud, r.Word(hud));
        for (std::size_t i = 0; i < hud_count; ++i) { if (huds[i] == hud) { return false; } }
        huds[hud_count++] = hud; previous = node; node = r.Word(node);
    }
    if (!r.ok || previous != tail || !hud_count
        || std::find(huds.begin(), huds.begin() + hud_count, s.menu) == huds.begin() + hud_count) { return false; }
    for (std::size_t i = 0; i < hud_count; ++i) {
        if (r.Word(huds[i]) == r.base + 0x116BF7C) {
            if (s.recipe) { return false; }
            s.recipe = huds[i]; r.Require(s.recipe + 0x3B8, s.manager);
            r.Require(s.recipe + 0x3C0, s.vendor); r.Require(s.recipe + 0x3C4, 42);
            const auto selected = r.Word(s.recipe + 0x408);
            if (selected) {
                r.Require(selected, r.base + 0x1142748); s.item_template = r.Word(selected + 0x10);
                r.Require(selected + 0x14, 0);
            }
            const auto sentinel = r.Word(s.recipe + 0x400);
            s.prefix = r.Word(s.recipe + 0x40C); s.suffix = r.Word(s.recipe + 0x434);
            s.mode = r.Word(s.recipe + 0x404); s.table = r.Word(s.recipe + 0x47C);
            s.quantity = r.Word(s.recipe + 0x4D4); s.multiple = r.Word(s.recipe + 0x3D8) & 0xff;
            if (sentinel != 3362971591U || s.multiple > 1) { return false; }
        }
    }
    std::array<std::uint32_t, 512> children{};
    const auto child_count = r.Vector(s.menu + 0x54, children);
    std::uint32_t production_list = 0;
    for (std::size_t i = 0; r.ok && i < child_count; ++i) {
        const auto child = children[i]; r.Require(child + 0x3BC, s.menu);
        if (r.Word(child) != r.base + 0x116ACF0) { continue; }
        std::array<std::uint32_t, 128> controls{};
        const auto count = r.Vector(child + 0x408, controls);
        for (std::size_t j = 0; r.ok && j < count; ++j) {
            const auto control = controls[j];
            r.Require(control, r.base + 0x116AEBC); r.Require(control + 0x3BC, s.menu);
            r.Require(control + 0x458, child);
            const auto entry = r.Word(control + 0x44C);
            if (!entry || r.Word(entry) != r.base + 0x1169560) { continue; }
            if ((production_list && production_list != child) || s.count == s.slots.size()) { return false; }
            production_list = child;
            const auto item = r.Word(entry + 0x10), type = r.Word(entry + 0x14), flags = r.Word(entry + 0x58);
            const auto complete = flags & 0xff, active = (flags >> 8) & 0xff, modified = (flags >> 16) & 0xff;
            if (complete > 1 || active > 1 || modified > 1
                || (!item && (type || complete || active)) || (item && (type != 40 || !active))) { return false; }
            s.slots[s.count++] = {entry, item, item ? (complete ? 2U : 1U) : 0U};
        }
    }
    const auto inventory = r.Word(s.manager + 0x7C);
    if (inventory && std::find(huds.begin(), huds.begin() + hud_count, inventory) != huds.begin() + hud_count) {
        s.inventory = inventory;
        r.Require(inventory, r.base + 0x116C64C); r.Require(inventory + 0x104, s.manager);
        r.Require(inventory + 0x3F4, s.manager);
        if (find_item) {
            const auto listing = r.Word(inventory + 0x3F0);
            const auto count = r.Vector(inventory + 0x54, children);
            if (std::find(children.begin(), children.begin() + count, listing) == children.begin() + count) { return false; }
            r.Require(listing, r.base + 0x116ACF0); r.Require(listing + 0x3BC, inventory);
            std::array<std::uint32_t, 128> controls{}, item_ids{};
            const auto items = r.Vector(listing + 0x408, controls);
            for (std::size_t i = 0; r.ok && i < items; ++i) {
                const auto control = controls[i]; r.Require(control, r.base + 0x116AEBC);
                r.Require(control + 0x3BC, inventory); r.Require(control + 0x458, listing);
                const auto entry = r.Word(control + 0x44C); r.Require(entry, r.base + 0x11696C8);
                const auto item = r.Word(entry + 0x10); r.Require(entry + 0x14, 40);
                if (!item || std::find(item_ids.begin(), item_ids.begin() + i, item) != item_ids.begin() + i) { return false; }
                item_ids[i] = item;
                const auto instance = r.Word(entry + 0x20), native = r.Word(entry + 0x24);
                r.Require(instance, r.base + 0x114BB68); r.Require(native, r.base + 0x1142748);
                r.Require(instance + 0x18, item); r.Require(instance + 0x1C, 40);
                r.Require(native + 0x18, item); r.Require(native + 0x1C, 40);
                const auto item_template = r.Word(instance + 0x10);
                if (!item_template) { return false; }
                r.Require(instance + 0x14, 0); r.Require(native + 0x10, item_template); r.Require(native + 0x14, 0);
                inventory_contains |= item == find_item;
            }
        }
    }
    top_menu = front && (front == s.menu || front == s.recipe || front == s.inventory);
    std::sort(s.slots.begin(), s.slots.begin() + s.count, [](const auto& a, const auto& b) { return a.entry < b.entry; });
    s.revision = 1;
    if (!r.ok || !wire::ValidSnapshot(s) || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    s.revision = 0; out = s; return true;
}
bool InvokeNative(std::uintptr_t base, wire::Verb verb, const wire::Snapshot& s, std::uint32_t item) noexcept {
    using EmptyString = void* (__thiscall*)(void*);
    using DestroyString = void (__thiscall*)(void*);
    using Create = void (__thiscall*)(void*, const void*);
    struct ItemReference { std::uint32_t id, type; };
    using Keep = void (__thiscall*)(void*, ItemReference);
    __try {
        if (verb == wire::Verb::create) {
            alignas(4) unsigned char name[24]{};
            reinterpret_cast<EmptyString>(base + 0x145000)(name);
            reinterpret_cast<Create>(base + 0x63CE40)(reinterpret_cast<void*>(s.recipe), name);
            reinterpret_cast<DestroyString>(base + 0x145310)(name);
        } else if (verb == wire::Verb::keep) {
            reinterpret_cast<Keep>(base + 0x6D7080)(reinterpret_cast<void*>(s.manager), {item, 40});
        } else { return false; }
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
}
