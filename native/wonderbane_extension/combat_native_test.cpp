#include "combat_native.h"
#undef NDEBUG
#include <cassert>
#include <map>
#include <stdexcept>
#include <vector>
namespace c = wonderbane::extension::combat;
namespace m = wonderbane::extension::movement;
namespace s = c::submission;
using O = c::wire::Outcome;
namespace {
std::uintptr_t base = 0;
bool live = true, admitted = true, entered = true, ready = true;
bool invalidate_select = false, invalidate_query = false, invalidate_release = false;
bool throw_select = false, throw_release = false, cancel_rejected = false, seh_dispatch = false;
bool scoped = false;
unsigned restored = 0;
unsigned selections = 0, dispatches = 0, cancellations = 0, entries = 0, allocations = 0;
std::map<void*, unsigned> references;
std::vector<void*> objects;
s::Receipt submitted{s::Result::queued, true, true, true};
s::Context scope_context{};
void Word(std::uintptr_t at, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(at), &value, 4); }
bool Admit(void*) noexcept { return admitted; }
bool Enter(void*) noexcept { ++entries; return entered; }
void Text(std::uintptr_t field, std::uintptr_t storage, const wchar_t* value) {
    const auto bytes = (wcslen(value) + 1) * 2;
    std::memcpy(reinterpret_cast<void*>(storage), value, bytes);
    Word(field + 4, storage); Word(field + 8, storage + bytes - 2); Word(field + 12, storage + bytes);
}
c::wire::Command Command() {
    c::wire::Command command{};
    command.local_key[0] = 100; command.local_key[1] = 53;
    command.target_key[0] = 200; command.target_key[1] = 53;
    const c::wire::Text local{reinterpret_cast<const std::uint16_t*>(L"Local"), 5};
    const c::wire::Text shard{reinterpret_cast<const std::uint16_t*>(L"Shard"), 5};
    const c::wire::Text target{reinterpret_cast<const std::uint16_t*>(L"Target"), 6};
    assert(c::wire::IdentityDigest(local.units, local.count, command.local_name));
    assert(c::wire::IdentityDigest(shard.units, shard.count, command.server));
    assert(c::wire::IdentityDigest(target.units, target.count, command.target_name));
    c::wire::IdentityJson owner, entry;
    assert(owner.Literal("[\"Shard\", \"Local\"]") && owner.Finish(command.owner));
    assert(entry.Literal("[\"player\", \"Shard\", \"000000c8:00000035\"]") && entry.Finish(command.entry));
    return command;
}
m::NativeScene Reset() {
    assert(!allocations);
    references.clear(); objects = {reinterpret_cast<void*>(base + 0x4000)};
    live = admitted = entered = ready = true;
    invalidate_select = invalidate_query = invalidate_release = false;
    throw_select = throw_release = cancel_rejected = seh_dispatch = false;
    selections = dispatches = cancellations = entries = 0;
    submitted = {s::Result::queued, true, true, true};
    m::NativeScene scene{}; scene.epoch = 1; scene.window = base + 0x1000;
    scene.actor = base + 0x2000; scene.world = base + 0x6000; scene.parent = base + 0x7000;
    scene.identity = {100, 53};
    Word(base + 0x16a2d98, scene.actor); Word(base + 0x16a7bfc, scene.window);
    Word(base + 0x1389028, scene.world); Word(base + 0x16a2da4, 0);
    Word(base + 0x16ab88c, base + 0xa000); Word(base + 0xa044, base + 0xa100);
    Word(scene.window + 0x98, base + 0x8000); Word(base + 0x809c, base + 0x8100);
    Word(base + 0x8100, base + 0x8100); Word(base + 0x8104, base + 0x8100);
    Word(base + 0x11416b4, base + 0xa3d0);
    for (const auto offset : {0x2000U, 0x4000U}) {
        Word(base + offset, base + 0x114165c); Word(base + offset + 8, base + 0x9000);
        Word(base + 0x9004, 0x80);
        Word(base + offset + 0x18, offset == 0x2000 ? 100 : 200);
        Word(base + offset + 0x1c, 53);
        Text(base + offset + 0xc48, base + offset + 0xd00, offset == 0x2000 ? L"Local" : L"Target");
        Text(base + offset + 0xc90, base + offset + 0xd80, L"Shard");
    }
    Word(scene.actor + 0x4b0, base + 0xb000); Word(base + 0xb000, base + 0xb100);
    Word(base + 0xb108, scene.parent);
    const m::GroundPoint point{2000, 40, -3000};
    std::memcpy(reinterpret_cast<void*>(base + 0xb120), &point, sizeof(point));
    Word(scene.actor + 0xad0, base + 0xc000); Word(base + 0xc018, 1); Word(base + 0xc020, 1);
    Word(scene.actor + 0xaf8, 0);
    return scene;
}
}
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept { return live && scene.epoch == 1; }
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
}
namespace wonderbane::extension::combat::submission {
bool Ready() noexcept { return ready; }
Boundary::Boundary() noexcept {}
void Boundary::Restore() noexcept { scoped = false; ++restored; }
Scope::Scope(const Context& context) noexcept { scope_context = context; scoped = true; }
Scope::~Scope() { scoped = false; }
Receipt Scope::Finish() noexcept { return submitted; }
}
namespace wonderbane::extension::combat {
struct NativeTargetTestAccess {
    using Node = NativeTarget::Node; using List = NativeTarget::List;
    static List* __fastcall Construct(List* list, void*, const unsigned char*) {
        list->sentinel = new Node{}; ++allocations;
        list->sentinel->next = list->sentinel->previous = list->sentinel; return list;
    }
    static void __fastcall Query(void*, void*, const m::GroundPoint* minimum,
        const m::GroundPoint* maximum, List* list) {
        assert(minimum->x == 976 && maximum->x == 3024);
        for (auto* object : objects) {
            auto* node = new Node{list->sentinel, list->sentinel->previous, object}; ++allocations;
            list->sentinel->previous->next = node; list->sentinel->previous = node; ++references[object];
        }
        if (invalidate_query) { live = false; }
    }
    static void __fastcall Retain(void* adjusted, void*, void** slot) {
        assert(reinterpret_cast<std::uintptr_t>(adjusted) == reinterpret_cast<std::uintptr_t>(*slot) + 0x88);
        ++references[*slot];
    }
    static void __fastcall Release(void** slot, void*, void*) {
        if (*slot) { assert(references[*slot]); --references[*slot]; *slot = nullptr; }
        if (invalidate_release) { admitted = false; }
        if (throw_release) { throw std::runtime_error("release"); }
    }
    static void __cdecl Pool(void* value, std::uint32_t size) {
        assert(size == sizeof(Node)); delete static_cast<Node*>(value); --allocations;
    }
    static void __cdecl Select(void* value) {
        ++selections; assert(references[value] == 2); --references[value];
        Word(base + 0x16a2da4, reinterpret_cast<std::uintptr_t>(value));
        if (invalidate_select) { admitted = false; }
        if (throw_select) { throw std::runtime_error("select"); }
    }
    static bool __cdecl Dispatch(const void* tuple, void* root) {
        assert(root == reinterpret_cast<void*>(base + 0x1000));
        const auto* words = static_cast<const std::uint32_t*>(tuple);
        for (unsigned i = 1; i < 9; ++i) { assert(!words[i]); }
        if (words[0] == 0x616) {
            ++cancellations;
            if (!cancel_rejected) { Word(base + 0xc018, 1); Word(base + 0xc020, 1); Word(base + 0x2af8, 0); }
        } else {
            assert(words[0] == 0x60f); ++dispatches;
            if (seh_dispatch) {
                assert(scope_context.receipt); *scope_context.receipt = submitted;
                RaiseException(0xe0004342, 0, 0, nullptr);
            }
            assert(scope_context.current(scope_context.context));
            assert(scope_context.append_current(scope_context.context));
        }
        return true; // Dispatcher acceptance alone does not establish submission.
    }
    static void Bind(NativeTarget& target, HWND window) {
        target.base_ = base; target.window_ = window; target.thread_ = GetCurrentThreadId();
        target.calls_.construct = reinterpret_cast<decltype(target.calls_.construct)>(&Construct);
        target.calls_.query = reinterpret_cast<decltype(target.calls_.query)>(&Query);
        target.calls_.retain = reinterpret_cast<decltype(target.calls_.retain)>(&Retain);
        target.calls_.release = reinterpret_cast<decltype(target.calls_.release)>(&Release);
        target.calls_.pool_return = &Pool; target.calls_.select = &Select; target.calls_.dispatch = &Dispatch;
    }
    static void DisposeQuarantine(NativeTarget& target) {
        // Only fixture disposal, after proving production cannot retry faulted references.
        throw_release = false;
        if (target.actor_) { Release(&target.actor_, nullptr, nullptr); }
        if (target.target_) { Release(&target.target_, nullptr, nullptr); }
    }
};
}
int main() {
    auto* memory = VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    assert(memory); base = reinterpret_cast<std::uintptr_t>(memory);
    auto window = CreateWindowExW(0, L"STATIC", L"combat-native-test", 0, 0, 0, 1, 1,
        HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr); assert(window);
    auto command = Command(); auto scene = Reset();
    auto run = [&](O expected) {
        c::NativeTarget target; c::NativeTargetTestAccess::Bind(target, window);
        const auto result = target.Attack(scene, command, Admit, Enter, Admit, nullptr);
        assert(result.outcome == expected);
        if (seh_dispatch) { assert(result.queued); }
        if (throw_select || seh_dispatch) {
            assert(!target.Available() && !target.Clear());
            c::NativeTargetTestAccess::DisposeQuarantine(target);
        } else { assert(target.Clear()); }
        assert(!allocations);
        for (const auto& [object, refs] : references) { (void)object; assert(!refs); }
    };
    run(O::client_outbound_queued); assert(selections == 1 && entries == 1 && dispatches == 1);
    scene = Reset(); submitted = {}; run(O::native_rejected); assert(dispatches == 1);
    scene = Reset(); objects.clear(); run(O::stale); assert(!selections);
    scene = Reset(); objects.push_back(objects[0]); run(O::stale); assert(!selections);
    scene = Reset(); invalidate_query = true; run(O::stale); assert(!selections);
    scene = Reset(); invalidate_select = true; run(O::stale); assert(selections == 1 && !entries && !dispatches);
    scene = Reset(); entered = false; run(O::stale); assert(entries == 1 && !dispatches);
    scene = Reset(); admitted = false; run(O::stale); assert(!selections);
    scene = Reset(); Word(base + 0x4c54, base + 0x4d0c); run(O::stale); assert(!selections); // No terminator capacity.
    scene = Reset(); Word(base + 0x4d0c, 1); run(O::stale); assert(!selections); // Nonzero terminator.
    scene = Reset(); Word(base + 0x401c, 54); run(O::stale); assert(!selections);
    scene = Reset(); Word(base + 0x4d00, 'X'); run(O::stale); assert(!selections); // Full name, not key alone.
    scene = Reset(); Word(base + 0x4d80, 'X'); run(O::stale); assert(!selections); // Exact server identity.
    scene = Reset();
    Word(base + 0x8100, base + 0x8200); Word(base + 0x8104, base + 0x8200);
    Word(base + 0x8200, base + 0x8100); Word(base + 0x8204, base + 0x8100); Word(base + 0x8208, base + 0x8300);
    Word(base + 0x8310, 200); Word(base + 0x8314, 53); Word(base + 0x8374, 0x15);
    run(O::stale); assert(!selections); // Current party protection overrides the saved list.
    scene = Reset(); Word(base + 0x11416b4, 0); run(O::stale); assert(!selections);
    scene = Reset(); throw_select = true; run(O::unavailable); assert(!dispatches);
    scene = Reset(); seh_dispatch = true; const auto before_restore = restored;
    run(O::uncertain); assert(!scoped && restored == before_restore + 1);
    scene = Reset(); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target, window);
    c::NativeTarget::State state{};
    assert(target.Cancel(scene, Admit, nullptr, state) && !cancellations);
    Word(base + 0xc018, 2); Word(base + 0xc020, 4); Word(base + 0x2af8, base + 0x4000);
    cancel_rejected = true;
    assert(!target.Cancel(scene, Admit, nullptr, state) && cancellations == 1);
    cancel_rejected = false;
    assert(target.Cancel(scene, Admit, nullptr, state) && cancellations == 2);
    admitted = false; Word(base + 0xc018, 2);
    assert(!target.Cancel(scene, Admit, nullptr, state) && cancellations == 2);
    scene = Reset(); c::NativeTarget cleanup; c::NativeTargetTestAccess::Bind(cleanup, window);
    assert(cleanup.Attack(scene, command, Admit, Enter, Admit, nullptr).queued);
    assert(!cleanup.CombatTargetCurrent());
    Word(scene.actor + 0xaf8, base + 0x4000); assert(cleanup.CombatTargetCurrent());
    Word(scene.actor + 0xaf8, base + 0x6000); assert(!cleanup.CombatTargetCurrent());
    throw_release = true;
    assert(!cleanup.Clear() && !cleanup.Available() && !cleanup.Clear());
    c::NativeTargetTestAccess::DisposeQuarantine(cleanup);
    assert(DestroyWindow(window)); assert(VirtualFree(memory, 0, MEM_RELEASE));
}
