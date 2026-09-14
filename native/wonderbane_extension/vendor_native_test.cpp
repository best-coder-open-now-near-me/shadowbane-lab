#include "vendor_native.h"
#include <Windows.h>
#include <cstring>
#undef NDEBUG
#include <cassert>
namespace w = wonderbane::extension::vendor::wire;
namespace v = wonderbane::extension::vendor;
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
    const auto listing = base + 0x4000, control = base + 0x5000, entry = base + 0x6000;
    const auto hireling = base + 0x7000, recipe = base + 0x8000, item = base + 0x9000;
    const auto head = base + 0xa000, node = base + 0xa100, node2 = base + 0xa200;
    const auto children = base + 0xb000, controls = base + 0xb100;
    auto word = [](std::uint32_t at, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(at), &value, 4); };
    word(base + 0x16A7BFC, root); word(root, base + 0x1174884); word(root + 0x64, 2);
    word(root + 0xA4, manager); word(manager, base + 0x1171ADC); word(manager + 0x78, hud);
    word(hud, base + 0x116A058); word(hud + 0x104, manager);
    word(manager + 0xF0, 2229645); word(manager + 0xF4, 8);
    word(manager + 0xF8, 2229645); word(manager + 0xFC, 8);
    word(manager + 0x384, hireling); word(hireling, base + 0x1169518);
    word(hireling + 0x10, 2517204); word(hireling + 0x14, 42);
    word(root + 0x20, head); word(head, node); word(head + 4, node2);
    word(node, node2); word(node + 4, head); word(node + 8, recipe);
    word(node2, head); word(node2 + 4, node); word(node2 + 8, hud);
    word(recipe, base + 0x116BF7C); word(recipe + 0x3B8, manager);
    word(recipe + 0x3C0, 2517204); word(recipe + 0x3C4, 42);
    word(recipe + 0x408, item); word(item, base + 0x1142748); word(item + 0x10, 26990);
    word(recipe + 0x400, 3362971591U); word(recipe + 0x40C, 3362971591U);
    word(recipe + 0x434, 3362971591U); word(recipe + 0x404, 1);
    word(recipe + 0x47C, 12); word(recipe + 0x4D4, 1);
    word(hud + 0x54, children); word(hud + 0x58, children + 4); word(hud + 0x5C, children + 4);
    word(children, listing); word(listing, base + 0x116ACF0); word(listing + 0x3BC, hud);
    word(listing + 0x408, controls); word(listing + 0x40C, controls + 4); word(listing + 0x410, controls + 8);
    word(controls, control); word(control, base + 0x116AEBC); word(control + 0x3BC, hud);
    word(control + 0x458, listing); word(control + 0x44C, entry); word(entry, base + 0x1169560);
    m::NativeScene scene{}; scene.epoch = 1; scene.window = root;
    w::Snapshot s{}; bool inventory = false, top = false;
    auto capture = [&]() { return v::Capture(base, scene, s, 0, inventory, top); };
    assert(capture() && top && !inventory && w::RandomScepter(s));
    assert(s.count == 1 && s.slots[0].state == 0 && s.vendor == 2517204);
    word(entry + 0x10, 4294925624U); word(entry + 0x14, 40); word(entry + 0x58, 0x10101);
    assert(capture() && s.slots[0].state == 2);
    word(control + 0x458, listing + 4); assert(!capture()); word(control + 0x458, listing);
    word(recipe + 0x3C0, 2517205); assert(!capture()); word(recipe + 0x3C0, 2517204);
    word(manager + 0xF8, 2229646); assert(!capture()); word(manager + 0xF8, 2229645);
    word(node2, node); assert(!capture()); word(node2, head);
    word(listing + 0x40C, controls + 8); word(controls + 4, control); assert(!capture());
    word(listing + 0x40C, controls + 4);
    live = false; assert(!capture()); live = true;
    word(root + 0x64, 0); assert(!capture()); word(root + 0x64, 2);
    assert(capture());
    assert(VirtualFree(allocation, 0, MEM_RELEASE));
}
