#include "city_window_native.h"
#include <array>
#include <cstring>
namespace wonderbane::extension::city_window {
namespace {
bool Read(std::uintptr_t address, void* out, std::size_t size) noexcept {
    if (address < 0x10000 || address % 4 || address >= 0x80000000
        || !size || size > 8192 || size > 0x80000000 - address) { return false; }
    __try { std::memcpy(out, reinterpret_cast<void*>(address), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Reader {
    bool ok = true;
    std::uint32_t Word(std::uintptr_t p) noexcept {
        std::uint32_t out = 0; ok = Read(p, &out, 4) && ok; return out;
    }
    void Require(std::uintptr_t p, std::uint32_t value) noexcept { ok = Word(p) == value && ok; }
};
}
bool Capture(std::uintptr_t base, const movement::NativeScene& scene, wire::Snapshot& out) noexcept {
    out = {};
    if (!base || base > UINT32_MAX || !scene.epoch || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    Reader r; wire::Snapshot s{}; s.scene = scene.epoch;
    s.root = r.Word(base + 0x16A7BFC);
    if (s.root != scene.window) { return false; }
    r.Require(s.root, static_cast<std::uint32_t>(base + 0x1174884)); r.Require(s.root + 0x64, 2);
    s.manager = r.Word(s.root + 0xD4);
    r.Require(s.manager, static_cast<std::uint32_t>(base + 0x1171BCC));
    s.active_manager = r.Word(base + 0x16A7C1C);
    s.hud = r.Word(s.manager + 0x4C); s.mode = r.Word(s.manager + 0x44);
    s.building_count = r.Word(s.manager + 0x78);
    if (s.hud) {
        r.Require(s.hud, static_cast<std::uint32_t>(base + 0x1166234));
        r.Require(s.hud + 0x104, s.manager);
        s.loading = (r.Word(s.hud + 0x568) >> 16) & 0xff;
    }
    const auto head = r.Word(s.root + 0x20), tail = r.Word(head + 4);
    auto node = r.Word(head), previous = head;
    std::array<std::uint32_t, 128> seen{}, huds{}; std::size_t count = 0;
    while (r.ok && node != head) {
        if (count == seen.size()) { return false; }
        const auto hud = r.Word(node + 8);
        for (std::size_t i = 0; i < count; ++i) {
            if (seen[i] == node || huds[i] == hud) { return false; }
        }
        seen[count] = node; huds[count++] = hud;
        r.Require(node + 4, previous);
        if (s.hud && hud == s.hud) { s.visible = 1; }
        previous = node; node = r.Word(node);
    }
    if (!r.ok || previous != tail || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    auto checked = s; checked.revision = 1;
    if (!wire::ValidSnapshot(checked)) { return false; }
    out = s; return true;
}
bool InvokeOpen(std::uintptr_t base, const wire::Snapshot& expected) noexcept {
    // Ordinary cdecl action handler, restricted to action 0x334. That branch
    // installs the active manager and calls its Open(root), which requests the roster.
    if (!base || base > UINT32_MAX || !wire::ValidSnapshot(expected) || expected.loading) { return false; }
    __try {
        const std::array<std::uint32_t, 9> action{0x334};
        using Dispatch = bool (__cdecl*)(const void*, void*);
        return reinterpret_cast<Dispatch>(base + 0x7CA9C0)(
            action.data(), reinterpret_cast<void*>(expected.root));
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
}
