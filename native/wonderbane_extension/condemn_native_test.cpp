#include "condemn_native.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <cwchar>
namespace c = wonderbane::extension::condemn::native;
namespace m = wonderbane::extension::movement;
std::uint32_t base = 0, opens = 0, adds = 0, enables = 0, selections = 0, admissions = 0;
bool live = true, deny = false, mutate_on_admit = false, bad_selection = false;
bool change_flag_on_select = false, expire_on_select = false;
unsigned refreshes = 0;
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return live && s.epoch == 1; }
}
void Word(std::uint32_t p, std::uint32_t v) { std::memcpy(reinterpret_cast<void*>(p), &v, 4); }
std::uint32_t Word(std::uint32_t p) { std::uint32_t v; std::memcpy(&v, reinterpret_cast<void*>(p), 4); return v; }
void Vector(std::uint32_t p, std::uint32_t data, std::initializer_list<std::uint32_t> values) {
    auto at = data; for (auto v : values) { Word(at, v); at += 4; }
    Word(p, data); Word(p + 4, at); Word(p + 8, at);
}
void Jump(std::uint32_t rva, std::uintptr_t target) {
    auto* p = reinterpret_cast<unsigned char*>(base + rva); p[0] = 0xe9;
    const auto rel = static_cast<std::int32_t>(target - (base + rva + 5)); std::memcpy(p + 1, &rel, 4);
}
bool Admit(void*) noexcept {
    ++admissions;
    if (mutate_on_admit && admissions == 2) { Word(base + 0x6000 + 0x3d0, 999); }
    return !deny;
}
bool __fastcall Open(void* self, void*, std::uint32_t a, std::uint32_t b) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x4000 && !a && !b); ++opens; return false;
}
void* __fastcall Assign(void* self, void*, const c::Key* value) {
    std::memcpy(self, value, 8); return self;
}
void __fastcall Select(void* self, void*, void* row) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x7000);
    Word(base + 0x7404, bad_selection ? 0 : reinterpret_cast<std::uint32_t>(row)); ++selections;
    if (change_flag_on_select) { Word(base + 0x9084, 0x10000); }
    if (expire_on_select) { live = false; }
}
// The reviewed 0x5B1C40 callback ends in RET 4, even though it ignores its event.
// Preserve that stack argument in the stub so an omitted argument is detected.
void __fastcall Selected(void* self, void*, std::uint32_t event) {
    ++refreshes;
    assert(event == 0);
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x6000);
    const auto row = Word(base + 0x7404);
    if (row) { Word(base + 0x63b8, Word(row + 0x44c)); }
}
void __fastcall Add(void* self, void*, std::uint32_t scope, std::uint32_t warrant) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x6000 && !warrant);
    assert(scope == 4 || scope == 5);
    for (unsigned i = 0; i < 3; ++i) {
        const bool wanted = i == (scope == 4 ? 1U : 2U);
        assert(Word(base + 0x63e0 + i * 8) == (wanted ? 200U : 0U));
        assert(Word(base + 0x63e4 + i * 8) == (wanted ? 23U : 0U));
    }
    ++adds;
}
void __fastcall Enable(void* self, void*) {
    assert(reinterpret_cast<std::uint32_t>(self) == base + 0x6000);
    assert(Word(base + 0x63b8) == base + 0x9000);
    assert(!Word(base + 0x9084)); ++enables;
}
void Fixture(bool kos = true, bool entry = true, unsigned scope = 5) {
    std::memset(reinterpret_cast<void*>(base + 0x1000), 0, 0x14000);
    opens = adds = enables = selections = admissions = 0;
    live = true; deny = mutate_on_admit = bad_selection = false;
    change_flag_on_select = expire_on_select = false; refreshes = 0;
    const auto root = base + 0x1000, manager = base + 0x2000, building = base + 0x3000;
    const auto button = base + 0x4000, head = base + 0x5000, bnode = base + 0x5100, knode = base + 0x5200;
    const auto hud = base + 0x6000, list = base + 0x7000, row = base + 0x8000, object = base + 0x9000;
    Word(base + 0x16a7bfc, root); Word(root, base + 0x1174884); Word(root + 0x64, 2);
    Word(root + 0xa4, manager); Word(manager, base + 0x1171adc); Word(manager + 0x48, 1);
    Word(manager + 0xf0, 100); Word(manager + 0xf4, 8); Word(manager + 0xf8, 100); Word(manager + 0xfc, 8);
    Word(manager + 0x68, building); Word(building, base + 0x116a058); Word(building + 0x104, manager);
    Vector(building + 0x54, base + 0xa000, {button});
    Word(button, base + 0x1169ec0); Word(button + 0x3bc, building); Word(button + 0x1d0, 0x59d);
    std::memcpy(reinterpret_cast<void*>(base + 0xa100), L"BTNKOS", 12);
    Word(button + 0x168, base + 0xa100); Word(button + 0x16c, base + 0xa10c); Word(button + 0x170, base + 0xa10c);
    Word(root + 0x20, head); Word(head, kos ? knode : bnode); Word(head + 4, bnode);
    Word(bnode, head); Word(bnode + 4, kos ? knode : head); Word(bnode + 8, building);
    Word(knode, bnode); Word(knode + 4, head); Word(knode + 8, hud);
    Word(base + 0x1168e94 + 0x12c, base + 0x3b5c);
    Word(hud, base + 0x1168e94); Word(hud + 0xdc, 0x39); Word(hud + 0x3d0, 100); Word(hud + 0x3d4, 8);
    Vector(hud + 0x54, base + 0xa200, {list}); Word(hud + 0x3c8, list);
    Word(list, base + 0x116acf0); Word(list + 0x3bc, hud);
    Vector(list + 0x408, base + 0xa300, entry ? std::initializer_list<std::uint32_t>{row} : std::initializer_list<std::uint32_t>{});
    Word(row, base + 0x116aebc); Word(row + 0x3bc, hud); Word(row + 0x458, list); Word(row + 0x44c, object);
    Word(object, base + 0x11693ec); Word(object + 8, 0x1d); Word(object + 0x10, 200); Word(object + 0x14, 23);
    Word(object + (scope == 4 ? 0x70 : 0x78), 200); Word(object + (scope == 4 ? 0x74 : 0x7c), 23);
    Jump(0x5f5440, reinterpret_cast<std::uintptr_t>(&Open));
    Jump(0x111ba0, reinterpret_cast<std::uintptr_t>(&Assign));
    Jump(0x613520, reinterpret_cast<std::uintptr_t>(&Select));
    Jump(0x5b1c40, reinterpret_cast<std::uintptr_t>(&Selected));
    Jump(0x5b04e0, reinterpret_cast<std::uintptr_t>(&Add));
    Jump(0x5b1640, reinterpret_cast<std::uintptr_t>(&Enable));
    FlushInstructionCache(GetCurrentProcess(), reinterpret_cast<void*>(base), 0x1800000);
}
int main() {
    base = reinterpret_cast<std::uint32_t>(VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE));
    assert(base);
    m::NativeScene scene{}; scene.epoch = 1; scene.window = base + 0x1000; scene.identity = {555, 53};
    c::Target target{{100, 8}, {200, 23}, 5}; c::Snapshot s{};
    Fixture(false); assert(c::Capture(base, scene, target, s));
    assert(c::Invoke(base, scene, target, c::Action::open, s, Admit, nullptr) == c::Result::submitted && opens == 1);
    Fixture(); assert(c::Capture(base, scene, target, s));
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::submitted);
    assert(enables == 1 && selections == 1 && refreshes == 1);
    for (const auto scope : {4U, 5U}) {
        Fixture(true, false, scope); target.scope = scope; assert(c::Capture(base, scene, target, s));
        assert(c::Invoke(base, scene, target, c::Action::add, s, Admit, nullptr) == c::Result::submitted && adds == 1);
        assert(!enables);
    }
    target.scope = 5;
    Fixture(); Word(base + 0x9084, 0x10000); assert(c::Capture(base, scene, target, s));
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::unavailable && !enables);
    Fixture(); assert(c::Capture(base, scene, target, s)); deny = true;
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::unavailable && !selections);
    Fixture(); assert(c::Capture(base, scene, target, s)); mutate_on_admit = true;
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::uncertain && !enables);
    Fixture(); assert(c::Capture(base, scene, target, s)); bad_selection = true;
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::uncertain && !enables);
    Fixture(); assert(c::Capture(base, scene, target, s)); live = false;
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::unavailable && !enables);
    for (bool* fault : {&change_flag_on_select, &expire_on_select}) {
        Fixture(); assert(c::Capture(base, scene, target, s)); *fault = true;
        assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::uncertain);
        assert(selections == 1 && !refreshes && !enables);
    }
    Fixture(); Word(base + 0x1168e94 + 0x12c, 0); assert(!c::Capture(base, scene, target, s));
    Fixture(true, true, 4); assert(c::Capture(base, scene, target, s)); assert(s.collision && !s.entry);
    assert(c::Invoke(base, scene, target, c::Action::add, s, Admit, nullptr) == c::Result::unavailable && !adds);
    for (const auto action : {c::Action::add, c::Action::enable}) {
        Fixture(true, action == c::Action::enable); Word(base + 0x63f8, 0x100);
        assert(c::Capture(base, scene, target, s));
        assert(c::Invoke(base, scene, target, action, s, Admit, nullptr) == c::Result::unavailable);
        assert(!adds && !enables);
    }
    for (const auto offset : {0x5004U, 0x2068U, 0x20f8U, 0x3104U, 0x63c8U, 0x73bcU, 0x83bcU, 0x8458U, 0x9008U}) {
        Fixture(); Word(base + offset, 1); assert(!c::Capture(base, scene, target, s));
    }
    Fixture(); Word(base + 0x9070, 200); Word(base + 0x9074, 23);
    assert(c::Capture(base, scene, target, s) && s.collision && !s.entry);
    Fixture(); Vector(base + 0x7408, base + 0xa300, {base + 0x8000, base + 0x8000});
    assert(!c::Capture(base, scene, target, s));
    Fixture(); Word(base + 0x63b8, base + 0x9100); assert(!c::Capture(base, scene, target, s));
    Fixture(); Word(base + 0x63d0, 101); assert(c::Capture(base, scene, target, s));
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::unavailable && !enables);
    Fixture(); assert(c::Capture(base, scene, target, s)); Word(base + 0x63d0, 101);
    assert(c::Invoke(base, scene, target, c::Action::enable, s, Admit, nullptr) == c::Result::unavailable && !enables);
    VirtualFree(reinterpret_cast<void*>(base), 0, MEM_RELEASE);
}
