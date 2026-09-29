#include "combat_party.h"
#undef NDEBUG
#include <cassert>
#include <functional>

namespace p = wonderbane::extension::combat::party;
namespace m = wonderbane::extension::movement;
namespace {
std::uintptr_t base = 0;
bool live = true;
unsigned checks = 0;
std::function<void(unsigned)> on_check;
void Word(std::uintptr_t at, std::uint32_t value) {
    std::memcpy(reinterpret_cast<void*>(at), &value, sizeof(value));
}
constexpr std::uintptr_t kWindow = 0x1000, kActor = 0x2000, kManager = 0x3000;
constexpr std::uintptr_t kSentinel = 0x4000, kNodes = 0x5000, kEntries = 0x6000;
m::NativeScene Reset(unsigned count = 2) {
    live = true; checks = 0; on_check = {};
    m::NativeScene scene{};
    scene.window = base + kWindow; scene.actor = base + kActor;
    scene.world = base + 0x8000; scene.parent = base + 0x9000;
    scene.identity = {3, 11}; scene.epoch = 7;
    Word(base + 0x16a7bfc, scene.window); Word(base + 0x16a2d98, scene.actor);
    Word(base + 0x1389028, scene.world);
    Word(scene.actor + 0x18, 3); Word(scene.actor + 0x1c, 11);
    Word(scene.window + 0x98, base + kManager);
    Word(base + kManager + 0x9c, base + kSentinel);
    Word(base + kSentinel, base + (count ? kNodes : kSentinel));
    Word(base + kSentinel + 4, base + (count ? kNodes + (count - 1) * 0x10 : kSentinel));
    for (unsigned i = 0; i < count; ++i) {
        const auto node = base + kNodes + i * 0x10;
        const auto entry = base + kEntries + i * 0x100;
        Word(node, i + 1 == count ? base + kSentinel : node + 0x10);
        Word(node + 4, i == 0 ? base + kSentinel : node - 0x10);
        Word(node + 8, entry);
        Word(entry + 0x10, 3); Word(entry + 0x14, 100 + i);
        Word(entry + 0x74, i == 0 ? 0x16 : 0x15);
    }
    return scene;
}
void Reject(const m::NativeScene& scene, p::Snapshot& out) {
    // A failed recapture must not preserve the last successful protection set.
    assert(!p::Capture(base, scene, out));
    assert(!out.valid && out.count == 0 && out.manager == 0);
    assert(p::Protected(out, {3, 777}));
}
}
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept {
    ++checks;
    if (on_check) { on_check(checks); }
    return live && scene.epoch == 7;
}
}
int main() {
    auto* memory = VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    assert(memory); base = reinterpret_cast<std::uintptr_t>(memory);
    auto scene = Reset(); p::Snapshot out{}, same{};
    assert(p::Capture(base, scene, out) && out.count == 2 && checks == 3);
    assert(p::Protected(out, {3, 100}) && p::Protected(out, {3, 101}));
    assert(p::Protected(out, scene.identity) && p::Protected(out, {}));
    assert(!p::Protected(out, {4, 100}) && !p::Protected(out, {3, 102}));
    assert(p::Capture(base, scene, same) && p::Equal(out, same));
    same.scene.epoch++; assert(!p::Equal(out, same));
    scene = Reset(0); assert(p::Capture(base, scene, out) && out.count == 0);
    assert(p::Protected(out, scene.identity) && !p::Protected(out, {3, 100}));
    scene = Reset(10); assert(p::Capture(base, scene, out) && out.count == 10);
    assert(p::Protected(out, {3, 109}));
    scene = Reset(11); Reject(scene, out);
    scene = Reset(); Word(base + kNodes + 0x10, base + kNodes); Reject(scene, out);
    scene = Reset(); Word(base + kNodes + 0x14, base + kSentinel); Reject(scene, out);
    scene = Reset(); Word(base + kSentinel + 4, base + kNodes); Reject(scene, out);
    scene = Reset(); Word(base + kEntries + 0x114, 100); Reject(scene, out);
    scene = Reset(); Word(base + kNodes + 0x18, base + kEntries); Reject(scene, out);
    scene = Reset(); Word(base + kEntries + 0x174, 0x16); Reject(scene, out);
    scene = Reset(); Word(base + kEntries + 0x74, 0x99); Reject(scene, out);
    scene = Reset(); Word(base + kEntries + 0x10, 0); Word(base + kEntries + 0x14, 0); Reject(scene, out);
    scene = Reset(); Word(base + kEntries + 0x10, 0); Reject(scene, out);
    scene = Reset(); Word(base + kEntries + 0x14, 0); Reject(scene, out);
    scene = Reset(); Word(base + kManager + 0x9c, 0); Reject(scene, out);
    scene = Reset(); Word(base + kNodes + 8, base + kEntries + 1); Reject(scene, out);
    scene = Reset(); Word(base + kNodes + 8, 0xfffffff0); Reject(scene, out);
    scene = Reset(); Word(base + 0x16a2d98, scene.actor + 0x100); Reject(scene, out);
    scene = Reset(); Word(base + 0x16a7bfc, scene.window + 0x100); Reject(scene, out);
    scene = Reset(); Word(base + 0x1389028, scene.world + 0x100); Reject(scene, out);
    scene = Reset(); Word(scene.actor + 0x1c, 12); Reject(scene, out);
    scene = Reset(); live = false; Reject(scene, out);
    // Change identity in place, retaining all list pointers, between passes.
    scene = Reset(); on_check = [](unsigned n) { if (n == 2) { Word(base + kEntries + 0x14, 999); } };
    Reject(scene, out);
    // Even a well-formed replacement list with the same keys is a new capture.
    scene = Reset(); on_check = [](unsigned n) {
        if (n == 2) {
            const auto replacement = base + 0xa000;
            std::memcpy(reinterpret_cast<void*>(replacement), reinterpret_cast<void*>(base + kEntries), 0x78);
            Word(base + kNodes + 8, replacement);
        }
    }; Reject(scene, out);
    scene = Reset(); on_check = [](unsigned n) { if (n == 3) { live = false; } }; Reject(scene, out);
    scene = Reset(); on_check = [](unsigned n) { if (n == 3) { Word(base + 0x16a7bfc, 0); } }; Reject(scene, out);
    scene = Reset(); DWORD old = 0;
    assert(VirtualProtect(reinterpret_cast<void*>(base + kEntries), 0x1000, PAGE_NOACCESS, &old));
    Reject(scene, out);
    assert(VirtualProtect(reinterpret_cast<void*>(base + kEntries), 0x1000, old, &old));
    assert(!p::Capture(0xfffffff0, scene, out) && !out.valid);
    assert(VirtualFree(memory, 0, MEM_RELEASE));
}
