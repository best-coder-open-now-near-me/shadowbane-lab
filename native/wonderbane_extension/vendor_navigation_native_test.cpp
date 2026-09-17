#include "vendor_navigation_native.h"
#include "guard_upgrade_native.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <cwchar>
namespace n = wonderbane::extension::vendor_navigation;
namespace m = wonderbane::extension::movement;
bool live = true;
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return live && s.epoch == 1; }
}
std::uint32_t callback_base = 0, selections = 0, activations = 0;
bool select_ok = true, detach_after_select = false, change_action = false;
void Put(std::uint32_t at, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(at), &value, 4); }
void __fastcall SelectRow(void* self, void*, void* row) {
    assert(reinterpret_cast<std::uint32_t>(self) == callback_base + 0x5000);
    assert(reinterpret_cast<std::uint32_t>(row) == callback_base + 0x6000);
    ++selections;
    if (select_ok) { Put(callback_base + 0x5404, reinterpret_cast<std::uint32_t>(row)); }
    if (detach_after_select) { Put(callback_base + 0x63bc, 0); }
    if (change_action) { Put(callback_base + 0x61d0, 0x583); }
}
bool __fastcall ActivateRow(void* self, void*, std::uint32_t event) {
    assert(reinterpret_cast<std::uint32_t>(self) == callback_base + 0x6000 && event == 0);
    ++activations; return true;
}
void Jump(std::uint32_t rva, std::uintptr_t target) {
    auto* code = reinterpret_cast<unsigned char*>(callback_base + rva);
    code[0] = 0xb8; Put(callback_base + rva + 1, static_cast<std::uint32_t>(target));
    code[5] = 0xff; code[6] = 0xe0;
    assert(FlushInstructionCache(GetCurrentProcess(), code, 7));
}
int main() {
    auto* memory = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE));
    assert(memory); const auto base = reinterpret_cast<std::uint32_t>(memory);
    callback_base = base;
    Jump(0x613520, reinterpret_cast<std::uintptr_t>(&SelectRow));
    Jump(0x61c7f0, reinterpret_cast<std::uintptr_t>(&ActivateRow));
    auto word = [](std::uint32_t p, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(p), &value, 4); };
    const auto root = base + 0x1000, manager = base + 0x2000, hud = base + 0x3000;
    const auto head = base + 0x4000, node = base + 0x4100, list = base + 0x5000;
    const auto control = base + 0x6000, vacancy = base + 0x7000, entry = base + 0x8000, empty = base + 0x9000;
    word(base + 0x16a7bfc, root); word(root, base + 0x1174884); word(root + 0x64, 2);
    word(root + 0xa4, manager); word(manager, base + 0x1171adc);
    word(root + 0x20, head); word(head, head); word(head + 4, head);
    m::NativeScene scene{}; scene.epoch = 1; scene.window = root;
    n::wire::Snapshot s{};
    auto capture = [&] { const bool ok = n::Capture(base, scene, s); s.revision = 1; return ok; };
    assert(capture() && !s.visible); // No manual menu prerequisite.
    word(manager + 0x68, hud); word(manager + 0xd0, 6); word(manager + 0x48, 1);
    word(hud, base + 0x116a058); word(hud + 0x104, manager);
    // A secondary panel may be the last dispatched manager while this HUD lives.
    word(base + 0x16a7c1c, base + 0xf000); word(head, node); word(head + 4, node);
    word(node, head); word(node + 4, head); word(node + 8, hud);
    word(manager + 0xf0, 123); word(manager + 0xf4, 8);
    word(manager + 0xf8, 123); word(manager + 0xfc, 8);
    word(manager + 0x380, 2); word(manager + 0x37c, 1);
    auto vector = [&](std::uint32_t at, std::uint32_t data, unsigned count) {
        word(at, data); word(at + 4, data + 4 * count); word(at + 8, data + 4 * count);
    };
    vector(hud + 0x54, base + 0xa000, 1); word(base + 0xa000, list);
    word(list, base + 0x116acf0); word(list + 0x3bc, hud);
    vector(list + 0x408, base + 0xa100, 2); word(base + 0xa100, control); word(base + 0xa104, vacancy);
    for (const auto row : {control, vacancy}) {
        word(row, base + 0x116aebc); word(row + 0x3bc, hud); word(row + 0x458, list);
    }
    word(control + 0x44c, entry); word(vacancy + 0x44c, empty);
    for (const auto row : {entry, empty}) { word(row, base + 0x1169518); word(row + 8, 9); }
    word(entry + 0x10, 777); word(entry + 0x14, 42); word(entry + 0x6c, 0x100);
    assert(capture() && s.visible == 1);
    std::uint32_t found = 0;
    auto find = [&] { return n::FindVendorControl(base, s, {777, 42}, found); };
    assert(find() && found == control);
    word(manager + 0x384, empty);
    assert(capture() && s.selected_entry == empty && s.vendor == n::wire::Key{});
    assert(n::wire::Opened(s, n::wire::Verb::building, {123, 8}) && find());
    assert(!n::wire::Opened(s, n::wire::Verb::vendor, {123, 8}, {777, 42}));
    word(empty + 0x10, 777); assert(!capture()); word(empty + 0x10, 0);
    word(empty + 0x6c, 0x100); assert(!capture());
    word(empty + 0x6c, 0x200); assert(!capture()); word(empty + 0x6c, 0);
    word(empty + 8, 8); assert(!capture()); word(empty + 8, 9);
    word(manager + 0x384, entry); assert(capture() && s.vendor[0] == 777);
    word(entry + 0x14, 8); assert(!capture()); word(entry + 0x14, 42);
    word(entry + 0x14, 37); assert(capture() && s.vendor[1] == 37);
    assert(!find());
    assert(!n::FindVendorControl(base, s, {777, 37}, found) && !found);
    assert(!n::FindGuardControl(base, s, {777, 42}, found) && !found);
    assert(n::FindGuardControl(base, s, {777, 37}, found) && found == control);
    assert(!n::InvokeVendor(base, s, {777, 37}));
    assert(!n::InvokeGuard(base, s, {777, 42}));
    // Mixed rosters preserve the distinction even with identical numeric IDs.
    word(empty + 0x10, 777); word(empty + 0x14, 42); word(empty + 0x6c, 0x100);
    word(manager + 0x37c, 2); assert(capture());
    assert(find() && found == vacancy);
    assert(n::FindGuardControl(base, s, {777, 37}, found) && found == control);
    word(empty + 0x14, 37); assert(!n::FindGuardControl(base, s, {777, 37}, found));
    word(empty + 0x10, 0); word(empty + 0x14, 0); word(empty + 0x6c, 0);
    word(manager + 0x37c, 1); word(entry + 0x14, 42);
    word(manager + 0x384, 0); assert(capture());
    word(control + 0x1a8, 1); assert(!find()); word(control + 0x1a8, 0);
    word(control + 0x458, list + 4); assert(!find()); word(control + 0x458, list);
    word(control + 0x3bc, hud + 4); assert(!find()); word(control + 0x3bc, hud);
    word(base + 0xa104, control); assert(!find()); word(base + 0xa104, vacancy);
    word(empty + 0x10, 777); word(empty + 0x14, 42); word(empty + 0x6c, 0x100);
    assert(!find()); word(empty + 0x10, 0); word(empty + 0x14, 0); word(empty + 0x6c, 0);
    word(entry + 8, 8); assert(!find()); word(entry + 8, 9);
    ++s.capacity; assert(!find()); --s.capacity;
    word(hud + 0x104, manager + 4); assert(!capture()); word(hud + 0x104, manager);
    word(manager + 0xf8, 456); assert(!capture()); word(manager + 0xf8, 123);
    word(node, node); assert(!capture()); word(node, head);
    live = false; assert(!capture()); live = true;
    assert(capture() && find());
    assert(!n::InvokeVendor(base, {}, {777, 42}));
    // Already selected rows still need event-zero activation, not another select.
    word(list + 0x404, control);
    assert(n::InvokeVendor(base, s, {777, 42}) && selections == 1 && activations == 1);
    word(list + 0x404, 0);
    assert(n::InvokeVendor(base, s, {777, 42}) && selections == 2 && activations == 2);
    word(entry + 0x14, 37); assert(capture());
    assert(n::InvokeGuard(base, s, {777, 37}) && selections == 3 && activations == 3);
    word(control + 0x1d0, 0x4ce);
    assert(n::InvokeGuard(base, s, {777, 37}) && activations == 4);
    word(control + 0x1d0, 0x583); // A different mapped action is never activated.
    assert(!n::InvokeGuard(base, s, {777, 37}) && selections == 4);
    word(control + 0x1d0, 0); word(control + 0x1d4, 1);
    assert(!n::InvokeGuard(base, s, {777, 37})); word(control + 0x1d4, 0);
    word(control + 0x1d8, 1);
    assert(!n::InvokeGuard(base, s, {777, 37})); word(control + 0x1d8, 0);
    word(control + 0x304, 0x100);
    assert(!n::InvokeGuard(base, s, {777, 37})); word(control + 0x304, 0);
    select_ok = false; word(list + 0x404, 0);
    assert(!n::InvokeGuard(base, s, {777, 37}) && activations == 4); select_ok = true;
    detach_after_select = true;
    assert(!n::InvokeGuard(base, s, {777, 37}) && activations == 4);
    detach_after_select = false; word(control + 0x3bc, hud);
    change_action = true;
    assert(!n::InvokeGuard(base, s, {777, 37}) && activations == 4);
    change_action = false; word(control + 0x1d0, 0);

    const auto warehouse = base + 0x15000, whnode = base + 0x16000, npc = base + 0x17000;
    word(warehouse, base + 0x1170308); word(warehouse + 0x378, npc);
    word(npc, base + 0x114165c); word(npc + 0x18, 777); word(npc + 0x1c, 42);
    word(head, whnode); word(whnode, node); word(whnode + 4, head); word(whnode + 8, warehouse);
    word(node + 4, whnode);
    assert(capture() && s.warehouse_hud == warehouse && s.warehouse_object == npc);
    assert(n::wire::Opened(s, n::wire::Verb::warehouse, {123, 8}, {777, 42}));
    assert(!n::wire::Opened(s, n::wire::Verb::warehouse, {456, 8}, {777, 42}));
    assert(!n::wire::Opened(s, n::wire::Verb::warehouse, {123, 8}, {778, 42}));
    // A front building menu must not erase the warehouse HUD's owned NPC.
    word(head, node); word(head + 4, whnode); word(node, whnode); word(node + 4, head);
    word(whnode, head); word(whnode + 4, node);
    assert(capture() && s.front_hud == hud && s.warehouse_hud == warehouse && s.warehouse_object == npc);
    assert(!n::wire::Opened(s, n::wire::Verb::warehouse, {123, 8}, {777, 42}));
    word(head, whnode); word(head + 4, node); word(whnode, node); word(whnode + 4, head);
    word(node, head); word(node + 4, whnode);
    word(npc + 0x1c, 37); assert(!capture()); word(npc + 0x1c, 42);
    word(npc, base + 0x1177c0c); assert(!capture()); word(npc, base + 0x114165c);
    word(warehouse + 0x378, 0); assert(!capture()); word(warehouse + 0x378, npc);
    word(node + 8, warehouse); assert(!capture()); word(node + 8, hud);
    word(head, node); word(node + 4, head); assert(capture() && !s.warehouse_hud);

    const auto ghud = base + 0x11000, gnode = base + 0x12000, children = base + 0x13000;
    word(manager + 0x78, ghud); word(manager + 0x50, 1); word(manager + 0x384, entry);
    word(entry + 0x14, 37); word(entry + 0x28, 1);
    word(ghud, base + 0x116a058); word(ghud + 0x104, manager);
    word(head, gnode); word(gnode, node); word(gnode + 4, head); word(gnode + 8, ghud);
    word(node + 4, gnode);
    vector(ghud + 0x54, children, 3);
    const wchar_t* names[] = {L"BTNUPGRADE", L"SLIDEUPGRADE", L"BTNUPGRADECOST"};
    for (unsigned i = 0; i < 3; ++i) {
        const auto button = base + 0x14000 + 0x1000 * i, text = base + 0x17000 + 0x100 * i;
        const auto length = static_cast<unsigned>(std::wcslen(names[i]) * 2);
        word(children + 4 * i, button); word(button, base + 0x1169ec0); word(button + 0x3bc, ghud);
        std::memcpy(reinterpret_cast<void*>(text), names[i], length);
        word(button + 0x168, text); word(button + 0x16c, text + length); word(button + 0x170, text + length);
    }
    const auto upgrade = base + 0x14000, progress = base + 0x15000;
    word(upgrade + 0x1d0, 0x58b); word(progress + 0x304, 0x100);
    word(manager + 0x274, 100); word(manager + 0x1cc, 150); word(manager + 0x2ac, 0x100);
    namespace g = wonderbane::extension::guard_upgrade;
    g::wire::Snapshot guard{}; bool top = false;
    auto capture_guard = [&] { const bool ok = g::Capture(base, scene, guard, top); guard.navigation.revision = 1; return ok; };
    assert(capture_guard() && top && g::wire::Eligible(guard));
    word(manager + 0x2ac, 0x101); assert(capture_guard() && !g::wire::Eligible(guard));
    word(progress + 0x304, 0); assert(capture_guard() && guard.control_flags == 7);
    word(manager + 0x2ac, 0x100); assert(capture_guard() && !g::wire::Eligible(guard));
    word(progress + 0x304, 0x100); word(manager + 0x1cc, 99);
    assert(capture_guard() && !g::wire::Eligible(guard));
    word(manager + 0x1cc, 150);
    word(upgrade + 0x1d0, 0x58a); assert(!capture_guard()); word(upgrade + 0x1d0, 0x58b);
    word(upgrade + 0x1d4, 20); assert(!capture_guard()); word(upgrade + 0x1d4, 0);
    word(base + 0x16000 + 0x3bc, hud); assert(!capture_guard()); word(base + 0x16000 + 0x3bc, ghud);
    word(manager + 0x50, 0); assert(!capture_guard()); word(manager + 0x50, 1);
    word(entry + 0x14, 42); assert(!capture_guard()); word(entry + 0x14, 37);
    word(manager + 0x2ac, 0x200); assert(!capture_guard()); word(manager + 0x2ac, 0x100);
    word(children + 8, upgrade); assert(!capture_guard()); word(children + 8, base + 0x16000);
    assert(capture_guard() && g::wire::Eligible(guard));
    live = false; assert(!capture_guard()); live = true;
    assert(!g::Invoke(base, {}));
    assert(VirtualFree(memory, 0, MEM_RELEASE));
}
