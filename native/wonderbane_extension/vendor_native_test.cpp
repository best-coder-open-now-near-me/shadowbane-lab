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
    w::RemainingCounts remaining{};
    auto capture = [&]() { return v::Capture(base, scene, s, 0, inventory, top, &remaining); };
    assert(capture() && top && !inventory && w::RandomScepter(s));
    const auto channel = base + 0x80000, channel_node = base + 0x81000;
    word(channel, base + 0x11659d8); word(channel_node + 8, channel);
    word(head, channel_node); word(channel_node + 4, head); word(channel_node, node);
    word(node + 4, channel_node);
    assert(capture() && top); // Chat ordering does not block a verified transaction window.
    word(channel, base + 0x1168044); assert(capture() && !top); // An amount dialog still blocks.
    word(channel, base + 0x1174884); assert(capture() && !top); // Unknown HUDs still block.
    word(channel_node, channel_node); assert(!capture()); // Still validate the complete owned list.
    word(channel_node, node); word(head, node); word(node + 4, head);
    assert(capture() && top);
    assert(s.count == 1 && s.slots[0].state == 0 && s.vendor == 2517204);
    word(entry + 0x10, 4294925624U); word(entry + 0x14, 40); word(entry + 0x58, 0x10101);
    assert(capture() && s.slots[0].state == 2);
    word(entry + 0x44, 9); assert(capture() && remaining[0] == 9);
    word(entry + 0x44, 0); assert(capture() && remaining[0] == 0);
    word(entry + 0x44, 256); assert(capture() && remaining[0] == 256); // Never truncate native data.
    word(entry + 0x44, 0);
    word(control + 0x458, listing + 4); assert(!capture()); word(control + 0x458, listing);
    word(recipe + 0x3C0, 2517205); assert(!capture()); word(recipe + 0x3C0, 2517204);
    word(manager + 0xF8, 2229646); assert(!capture()); word(manager + 0xF8, 2229645);
    word(node2, node); assert(!capture()); word(node2, head);
    word(listing + 0x40C, controls + 8); word(controls + 4, control); assert(!capture());
    word(listing + 0x40C, controls + 4);
    live = false; assert(!capture()); live = true;
    word(root + 0x64, 0); assert(!capture()); word(root + 0x64, 2);
    assert(capture());
    // Counts must follow sorted entry identities, not the UI control order.
    const auto control2 = base + 0x12000, entry2 = base + 0x13000;
    word(control2, base + 0x116AEBC); word(control2 + 0x3BC, hud);
    word(control2 + 0x458, listing); word(control2 + 0x44C, entry2);
    word(entry2, base + 0x1169560); word(entry2 + 0x10, 123); word(entry2 + 0x14, 40);
    word(entry2 + 0x58, 0x100); word(entry2 + 0x44, 3); word(entry + 0x44, 9);
    word(controls, control2); word(controls + 4, control); word(listing + 0x40C, controls + 8);
    assert(capture() && s.count == 2 && s.slots[0].entry == entry && s.slots[1].entry == entry2);
    assert(remaining[0] == 9 && remaining[1] == 3 && !remaining[2]);
    // A full sixteen-by-ten batch exceeds the old 128-item displayed-list bound.
    const auto inv = base + 0x14000, inv_list = base + 0x15000, inv_node = base + 0x16000;
    const auto inv_children = base + 0x17000, inv_controls = base + 0x18000;
    word(manager + 0x7c, inv); word(inv, base + 0x116c64c); word(inv + 0x104, manager);
    word(inv + 0x3f4, manager); word(inv + 0x3f0, inv_list);
    word(inv + 0x54, inv_children); word(inv + 0x58, inv_children + 4); word(inv + 0x5c, inv_children + 4);
    word(inv_children, inv_list); word(inv_list, base + 0x116acf0); word(inv_list + 0x3bc, inv);
    word(inv_list + 0x408, inv_controls); word(inv_list + 0x40c, inv_controls + 160 * 4);
    word(inv_list + 0x410, inv_controls + 160 * 4);
    word(head, inv_node); word(inv_node, node); word(inv_node + 4, head); word(inv_node + 8, inv);
    word(node + 4, inv_node);
    for (std::uint32_t i = 0; i < 160; ++i) {
        const auto c = base + 0x100000 + i * 0x1000, e = c + 0x500, instance = c + 0x600, native = c + 0x800;
        word(inv_controls + i * 4, c); word(c, base + 0x116aebc); word(c + 0x3bc, inv);
        word(c + 0x458, inv_list); word(c + 0x44c, e); word(e, base + 0x11696c8);
        word(e + 0x10, i + 1); word(e + 0x14, 40); word(e + 0x20, instance); word(e + 0x24, native);
        word(instance, base + 0x114bb68); word(native, base + 0x1142748);
        for (const auto p : {instance, native}) {
            word(p + 0x10, 26990); word(p + 0x14, 0); word(p + 0x18, i + 1); word(p + 0x1c, 40);
        }
    }
    assert(v::Capture(base, scene, s, 160, inventory, top, &remaining) && top && inventory);
    word(base + 0x100000 + 0x500 + 0x10, 160);
    word(base + 0x100000 + 0x600 + 0x18, 160);
    word(base + 0x100000 + 0x800 + 0x18, 160);
    assert(!v::Capture(base, scene, s, 160, inventory, top, &remaining)); // Duplicate IDs fail closed.
    assert(VirtualFree(allocation, 0, MEM_RELEASE));
}
