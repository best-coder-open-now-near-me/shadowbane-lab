#include "guard_funding_native.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <cwchar>
namespace f = wonderbane::extension::guard_funding;
namespace m = wonderbane::extension::movement;
bool live = true, setter_ok = true, invalidate_purse = false, select_ok = true;
std::uint32_t base = 0, purse = 500, confirmations = 0, admissions = 0, opened = 0;
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return live && s.epoch == 1; }
}
void Word(std::uint32_t p, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(p), &value, 4); }
void Text(std::uint32_t p, std::uint32_t data, const wchar_t* value) {
    const auto length = static_cast<std::uint32_t>(std::wcslen(value) * 2);
    std::memcpy(reinterpret_cast<void*>(data), value, length);
    Word(p + 4, data); Word(p + 8, data + length); Word(p + 12, data + length);
}
void Vector(std::uint32_t p, std::uint32_t data, std::initializer_list<std::uint32_t> values) {
    auto at = data; for (auto v : values) { Word(at, v); at += 4; }
    Word(p, data); Word(p + 4, at); Word(p + 8, at);
}
std::uint32_t __fastcall GetPurse(void* self, void*) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x2688);
    if (invalidate_purse) { live = false; }
    return purse;
}
void __fastcall SetAmount(void* self, void*, std::uint32_t amount) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x7000);
    assert(amount == 100);
    if (setter_ok) { Text(base + 0xa000 + 0xa4, base + 0x13000, L"100"); }
}
bool __fastcall Withdraw(void* self, void*, std::uint32_t event, std::uint32_t flag) {
    assert(!event && !flag);
    if (reinterpret_cast<std::uint32_t>(self) == base + 0x1d000) {
        std::uint32_t kind = 0, limit = purse;
        std::memcpy(&kind, reinterpret_cast<void*>(base + 0x3000), 4);
        if (kind == base + 0x1170308) {
            Word(base + 0x3000 + 0x10c, base + 0x7000);
            std::memcpy(&limit, reinterpret_cast<void*>(base + 0xc000 + 0x48), 4); limit -= 50;
        } else {
            Word(base + 0x15000 + 0x74, base + 0x7000); Word(base + 0x15000 + 0xd0, 13);
        }
        Word(base + 0x4000, base + 0x4200); Word(base + 0x4100 + 4, base + 0x4200);
        Word(base + 0x7000 + 0x3c0, limit);
        wchar_t text[20]{}; swprintf_s(text, L"%u", limit);
        Text(base + 0xa000 + 0xa4, base + 0x13000, text);
        ++opened; return false;
    }
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x8000);
    ++confirmations; return false; // Normal callback return is not an acceptance receipt.
}
bool __fastcall SelectGold(void* self, void*, std::uint32_t event, std::uint32_t flag) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0xb000 && event == 1 && !flag);
    const auto head = base + 0x1a000, node = base + 0x1b000;
    Word(base + 0x3000 + 0x3c8, 1); Word(head + 4, node); Word(head + 8, node); Word(head + 12, node);
    Word(node + 4, head); Word(node + 8, 0); Word(node + 12, 0);
    Word(node + 0x10, base + 0xc000 + (select_ok ? 0 : 4)); return true;
}
void __fastcall Deposit(void* self, void*, std::uint32_t mode) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x15000 && mode == 13);
    ++confirmations;
}
void Jump(std::uint32_t rva, std::uintptr_t target) {
    auto* code = reinterpret_cast<unsigned char*>(base + rva);
    code[0] = 0xb8; Word(base + rva + 1, static_cast<std::uint32_t>(target));
    code[5] = 0xff; code[6] = 0xe0;
    assert(FlushInstructionCache(GetCurrentProcess(), code, 7));
}
bool Admit(void*) noexcept { ++admissions; return live; }
int main() {
    auto* memory = VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    assert(memory); base = reinterpret_cast<std::uint32_t>(memory);
    const auto root = base + 0x1000, actor = base + 0x2000, hud = base + 0x3000;
    const auto head = base + 0x4000, hnode = base + 0x4100, qnode = base + 0x4200;
    const auto owner = base + 0x5000, list = base + 0x6000, quote = base + 0x7000;
    const auto accept = base + 0x8000, cancel = base + 0x9000, helper = base + 0xa000;
    const auto row = base + 0xb000, entry = base + 0xc000, header = base + 0xd000, reserve = base + 0xe000;
    Word(base + 0x16a7bfc, root); Word(root, base + 0x1174884); Word(root + 0x64, 2);
    Word(base + 0x16a2d98, actor); Word(actor + 0x18, 555); Word(actor + 0x1c, 1);
    Word(actor + 0x688, base + 0x11415e4); Word(base + 0x11415e4, base + 0x1686f);
    Word(base + 0x11415e8, base + 0x1c49f);
    Jump(0x4bc10, reinterpret_cast<std::uintptr_t>(&GetPurse));
    Jump(0x595720, reinterpret_cast<std::uintptr_t>(&SetAmount));
    Jump(0x5f5440, reinterpret_cast<std::uintptr_t>(&Withdraw));
    Jump(0x61c6e0, reinterpret_cast<std::uintptr_t>(&SelectGold));
    Jump(0x6cc3e0, reinterpret_cast<std::uintptr_t>(&Deposit));
    Word(root + 0x20, head); Word(head, qnode); Word(head + 4, hnode);
    Word(qnode, hnode); Word(qnode + 4, head); Word(qnode + 8, quote);
    Word(hnode, head); Word(hnode + 4, qnode); Word(hnode + 8, hud);
    Word(hud, base + 0x1170308); Word(hud + 0x378, owner); Word(hud + 0x10c, quote);
    Word(owner, base + 0x114165c); Word(owner + 0x18, 777); Word(owner + 0x1c, 42);
    Word(quote, base + 0x1168044); Word(quote + 0x108, hud); Word(quote + 0x388, 123);
    Word(quote + 0x3c0, 950);
    const auto opener = base + 0x1d000;
    Vector(hud + 0x54, base + 0x10000, {list, opener});
    Word(opener, base + 0x1169ec0); Word(opener + 0x3bc, hud);
    Word(opener + 0x1d0, 0x1008); Text(opener + 0x164, base + 0x1e000, L"WITHDRAW");
    for (const auto [offset, selection] : {std::pair{0x3c4U, base + 0x1a000}, {0x3dcU, base + 0x1c000}}) {
        Word(hud + offset, selection); Word(selection + 8, selection); Word(selection + 12, selection);
    }
    Word(list, base + 0x116acf0); Word(list + 0x3bc, hud);
    Text(list + 0x164, base + 0x10100, L"WAREHOUSE_INV");
    Vector(list + 0x408, base + 0x10200, {row});
    Word(row, base + 0x116aebc); Word(row + 0x3bc, hud); Word(row + 0x458, list); Word(row + 0x44c, entry);
    Word(entry, base + 0x116f258); Word(entry + 0x20, 123); Word(entry + 0x48, 1000);
    Text(entry + 0x30, base + 0x10300, L"Gold");
    Word(hud + 0x3e8, header); Word(hud + 0x3ec, 1);
    Word(header + 4, reserve); Word(header + 8, reserve); Word(header + 12, reserve);
    Word(reserve + 4, header); Word(reserve + 0x10, 123); Word(reserve + 0x14, 50);
    Vector(quote + 0x54, base + 0x10400, {accept, cancel, helper});
    const wchar_t* names[] = {L"ACCEPT", L"CANCEL", L"SLIDEHELPER"};
    for (unsigned i = 0; i < 3; ++i) {
        const auto control = accept + 0x1000 * i;
        Word(control, base + 0x1169ec0); Word(control + 0x3bc, quote);
        Text(control + 0x164, base + 0x11000 + 0x100 * i, names[i]);
    }
    Word(accept + 0x1d0, 0x1009); Word(cancel + 0x1d0, 0x100b);
    Text(helper + 0xa4, base + 0x13000, L"950");
    m::NativeScene scene{}; scene.actor = actor; scene.window = root; scene.epoch = 1; scene.identity = {555, 1};
    f::wire::Snapshot s{}; bool top = false;
    auto capture = [&](std::uint32_t direction = 1) { bool ok = f::Capture(base, scene, direction, s, top); s.revision = 1; return ok; };
    assert(capture() && top && s.balance == 1000 && s.reserve == 50 && s.purse == 500 && s.entered == 950);
    const auto warehouse = s;
    for (const auto [address, replacement] : {
        std::pair{owner + 0x1c, 8U}, {quote + 0x388, 124U}, {quote + 0x108, owner},
        {row + 0x458, hud}, {reserve + 4, reserve}, {reserve + 0x14, 51U},
        {header + 8, header}, {accept + 0x1d0, 0x100bU}, {helper + 0x304, 0x100U},
        {base + 0x11415e8, 0U}, {actor + 0x18, 556U}, {entry + 0x48, 999U}}) {
        std::uint32_t saved = 0; std::memcpy(&saved, reinterpret_cast<void*>(address), 4);
        Word(address, replacement); assert(!capture()); Word(address, saved);
    }
    invalidate_purse = true; assert(!capture()); invalidate_purse = false; live = true;
    purse = 0; assert(capture() && s.purse == 0); purse = 500;
    f::wire::Command c{}; c.host = {1, 1, 1}; c.window = 1000; c.request[0] = 1;
    c.expected = warehouse; c.direction = 1; c.amount = 100;
    setter_ok = false; assert(!f::Invoke(base, scene, c, &Admit, nullptr) && !confirmations);
    setter_ok = true; assert(f::Invoke(base, scene, c, &Admit, nullptr) && confirmations == 1);
    assert(capture() && s.entered == 100);
    c.expected = s; c.amount = 951; assert(!f::Invoke(base, scene, c, &Admit, nullptr) && confirmations == 1);
    Word(hud + 0x10c, 0); Word(head, hnode); Word(hnode + 4, head);
    assert(capture() && !s.quote && top && !f::wire::Eligible(s, 100));
    Word(entry + 0x48, 900); purse = 600;
    c.expected = warehouse; c.amount = 100; assert(capture() && f::wire::Confirmed(c, s));
    auto opening = c; opening.expected = s; opening.amount = 0;
    select_ok = false; assert(!f::InvokeOpen(base, scene, opening, &Admit, nullptr) && !opened);
    select_ok = true; assert(f::InvokeOpen(base, scene, opening, &Admit, nullptr) && opened == 1);
    assert(capture() && f::wire::Opened(opening, s) && confirmations == 1);
    Word(hud + 0x10c, 0); Word(head, hnode); Word(hnode + 4, head);
    // The deposit uses the exact current purse, not the limit cached at open.
    const auto manager = base + 0x15000;
    Word(root + 0xa4, manager); Word(manager, base + 0x1171adc); Word(manager + 0x48, 1);
    Word(manager + 0xd0, 13); Word(manager + 0xf0, 888); Word(manager + 0xf4, 8);
    Word(manager + 0xf8, 888); Word(manager + 0xfc, 8); Word(manager + 0x68, hud);
    Word(manager + 0x74, quote); Word(manager + 0x1cc, 25);
    Vector(hud + 0x54, base + 0x10000, {opener});
    Word(opener + 0x1d0, 0x586); Text(opener + 0x164, base + 0x1e000, L"BTNDEPOSIT");
    Word(hud, base + 0x116a058); Word(hud + 0x104, manager); Word(quote + 0x104, manager);
    Word(head, qnode); Word(hnode + 4, qnode); Word(quote + 0x3c0, 600);
    for (auto control : {accept, cancel}) {
        for (auto offset : {0x1d4U, 0x1f8U, 0x21cU}) { Word(control + offset, 13); }
    }
    Text(helper + 0xa4, base + 0x13000, L"100");
    assert(capture(2) && top && s.purse == 600 && s.balance == 25);
    c.expected = s; c.direction = 2;
    purse = 599; assert(!capture(2)); purse = 600;
    assert(f::Invoke(base, scene, c, &Admit, nullptr) && confirmations == 2);
    Word(manager + 0x74, 0); Word(manager + 0xd0, 0); Word(head, hnode); Word(hnode + 4, head);
    purse = 500; Word(manager + 0x1cc, 125);
    assert(capture(2) && f::wire::Confirmed(c, s));
    opening = c; opening.expected = s; opening.amount = 0;
    Word(opener + 0x1d0, 0x585); assert(!f::InvokeOpen(base, scene, opening, &Admit, nullptr) && opened == 1);
    Word(opener + 0x1d0, 0x586); assert(f::InvokeOpen(base, scene, opening, &Admit, nullptr) && opened == 2);
    assert(capture(2) && f::wire::Opened(opening, s) && confirmations == 2);
    Word(manager + 0xf8, 889); assert(!capture(2)); Word(manager + 0xf8, 888);
    live = false; assert(!capture(2)); assert(!f::Invoke(base, scene, c, &Admit, nullptr));
    assert(confirmations == 2 && admissions >= 4);
    assert(VirtualFree(memory, 0, MEM_RELEASE));
}
