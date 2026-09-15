#include "city_window_native.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
namespace c = wonderbane::extension::city_window;
namespace m = wonderbane::extension::movement;
bool live = true;
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return live && s.epoch == 1; }
}
int main() {
    auto* allocation = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(allocation);
    const auto base = reinterpret_cast<std::uint32_t>(allocation);
    const auto root = base + 0x1000, manager = base + 0x2000, hud = base + 0x3000;
    const auto head = base + 0x4000, node = base + 0x4100;
    auto word = [](std::uint32_t at, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(at), &value, 4); };
    word(base + 0x16A7BFC, root); word(root, base + 0x1174884); word(root + 0x64, 2);
    word(root + 0xD4, manager); word(manager, base + 0x1171BCC);
    word(root + 0x20, head); word(head, head); word(head + 4, head);
    m::NativeScene scene{}; scene.epoch = 1; scene.window = root;
    c::wire::Snapshot state{};
    auto capture = [&] { return c::Capture(base, scene, state); };
    assert(capture() && !state.hud && !state.visible); // No preparatory window needed.
    word(manager + 0x4C, hud); word(manager + 0x44, 2); word(hud, base + 0x1166234);
    word(hud + 0x104, manager); word(base + 0x16A7C1C, manager);
    word(head, node); word(head + 4, node);
    word(node, head); word(node + 4, head); word(node + 8, hud);
    assert(capture() && state.visible && state.active_manager == manager);
    word(hud + 0x568, 0x10000); assert(capture() && state.loading == 1);
    word(hud + 0x568, 0x20000); assert(!capture()); word(hud + 0x568, 0);
    word(node, node); assert(!capture()); word(node, head);
    word(node + 4, node); assert(!capture()); word(node + 4, head);
    word(hud + 0x104, manager + 4); assert(!capture()); word(hud + 0x104, manager);
    word(manager + 0x78, 513); assert(!capture()); word(manager + 0x78, 0);
    word(root + 0x64, 0); assert(!capture()); word(root + 0x64, 2);
    live = false; assert(!capture()); live = true;
    assert(capture());
    assert(!c::InvokeOpen(base, {})); // An unqualified snapshot cannot invoke a native entry.
    assert(VirtualFree(allocation, 0, MEM_RELEASE));
}
