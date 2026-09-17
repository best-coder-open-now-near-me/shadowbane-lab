#include "building_native_target.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <map>
#include <limits>
#include <stdexcept>
#include <thread>
#include <vector>
namespace n = wonderbane::extension::vendor_navigation;
namespace m = wonderbane::extension::movement;
using O = wonderbane::extension::vendor::wire::Outcome;
namespace {
bool live = true, admitted = true;
bool range_ok = true, invalidate_range = false, throw_open = false;
int range_checks = 0, warehouse_opens = 0;
m::GroundPoint expected_minimum{976, -2000, -4024}, expected_maximum{3024, 20000, -1976};
std::uintptr_t base = 0;
int selections = 0, dispatches = 0, queries = 0, allocations = 0;
bool invalidate_query = false, invalidate_release = false, invalidate_select = false;
bool throw_select = false, reject_dispatch = false, fault_query = false;
std::vector<void*> objects;
std::map<void*, int> references;
void Word(std::uintptr_t at, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(at), &value, 4); }
bool Admit(void*) noexcept { return admitted; }
}
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return live && s.epoch == 1; }
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
}
namespace wonderbane::extension::vendor_navigation {
struct BuildingTargetTestAccess {
    using Node = BuildingTarget::Node;
    using List = BuildingTarget::List;
    static List* __fastcall Construct(List* list, void*, const unsigned char*) {
        list->sentinel = new Node{}; ++allocations;
        list->sentinel->next = list->sentinel->previous = list->sentinel; return list;
    }
    static void __fastcall Query(void*, void*, const m::GroundPoint* minimum,
        const m::GroundPoint* maximum, List* list) {
        ++queries;
        assert(minimum->x == expected_minimum.x && minimum->y == expected_minimum.y && minimum->z == expected_minimum.z);
        assert(maximum->x == expected_maximum.x && maximum->y == expected_maximum.y && maximum->z == expected_maximum.z);
        if (fault_query) { throw std::runtime_error("query fault"); }
        for (auto* object : objects) {
            auto* node = new Node{list->sentinel, list->sentinel->previous, object}; ++allocations;
            list->sentinel->previous->next = node; list->sentinel->previous = node; ++references[object];
        }
        if (invalidate_query) { live = false; }
    }
    static void __fastcall Release(void** slot, void*, void*) {
        if (*slot) { assert(references[*slot] > 0); --references[*slot]; *slot = nullptr; }
        if (invalidate_release) { live = false; }
    }
    static void __cdecl Pool(void* value, std::uint32_t size) {
        assert(size == sizeof(Node)); delete static_cast<Node*>(value); --allocations;
    }
    static void __cdecl Select(void* object) {
        ++selections; assert(references[object] == 1); --references[object];
        Word(base + 0x16a2da4, reinterpret_cast<std::uintptr_t>(object));
        if (invalidate_select) { live = false; }
        if (throw_select) { throw std::runtime_error("after selection"); }
    }
    static bool __cdecl Dispatch(const void* value, void* root) {
        ++dispatches; assert(root == reinterpret_cast<void*>(base + 0x1000));
        const auto* words = static_cast<const std::uint32_t*>(value);
        assert(words[0] == 0x57c);
        for (int i = 1; i < 9; ++i) { assert(words[i] == 0); }
        return !reject_dispatch;
    }
    static bool __fastcall WarehouseRange(void* predicate, void*, void* actor, void* object) {
        ++range_checks;
        assert(*static_cast<std::uintptr_t*>(predicate) == base + 0x116a48c);
        assert(actor == reinterpret_cast<void*>(base + 0x2000) && references[object] == 1);
        if (invalidate_range) { admitted = false; }
        return range_ok;
    }
    static void __cdecl WarehouseOpen(void* actor, void* object) {
        ++warehouse_opens;
        assert(actor == reinterpret_cast<void*>(base + 0x2000) && references[object] == 1);
        if (throw_open) { throw std::runtime_error("warehouse entry fault"); }
        // Ordinary HUD retains its own reference; our borrowed argument is untouched.
    }
    static void Bind(BuildingTarget& target, HWND window) {
        target.base_ = base; target.window_ = window; target.thread_ = GetCurrentThreadId();
        target.calls_.construct = reinterpret_cast<decltype(target.calls_.construct)>(&Construct);
        target.calls_.query = reinterpret_cast<decltype(target.calls_.query)>(&Query);
        target.calls_.release = reinterpret_cast<decltype(target.calls_.release)>(&Release);
        target.calls_.pool_return = &Pool; target.calls_.select = &Select; target.calls_.dispatch = &Dispatch;
        target.calls_.warehouse_range = reinterpret_cast<decltype(target.calls_.warehouse_range)>(&WarehouseRange);
        target.calls_.warehouse_open = &WarehouseOpen;
    }
    static void DisposeQuarantine(BuildingTarget& target) {
        // Test-only disposal after checking that native uncertain cleanup is never retried.
        if (target.list_.sentinel) { delete target.list_.sentinel; --allocations; }
        if (target.held_) { Release(&target.held_, nullptr, nullptr); }
    }
};
}
int main() {
    auto* memory = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(memory); base = reinterpret_cast<std::uintptr_t>(memory);
    const auto window = CreateWindowExW(0, L"STATIC", L"building-target-test", 0, 0, 0, 1, 1,
        HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr);
    assert(window);
    m::NativeScene scene{}; scene.epoch = 1; scene.window = base + 0x1000;
    scene.actor = base + 0x2000; scene.world = base + 0x3000;
    Word(scene.actor, base + 0x4000); Word(base + 0x4058, base + 0xa3d0);
    Word(scene.actor + 0x4b0, base + 0x5000); Word(base + 0x5000, base + 0x6000);
    const m::GroundPoint world{2000, 40, -3000}, local{2, 3, 4};
    std::memcpy(memory + 0x6020, &world, sizeof(world));
    std::memcpy(memory + 0x6048, &local, sizeof(local));
    auto* first = memory + 0x8000; auto* second = memory + 0x9000;
    Word(reinterpret_cast<std::uintptr_t>(first), base + 0x1177c0c);
    Word(reinterpret_cast<std::uintptr_t>(second), base + 0x1177c0c);
    Word(reinterpret_cast<std::uintptr_t>(first) + 0x780, 123);
    Word(reinterpret_cast<std::uintptr_t>(first) + 0x784, 8);
    Word(reinterpret_cast<std::uintptr_t>(first) + 0x18, 999);
    Word(reinterpret_cast<std::uintptr_t>(second) + 0x18, 123); // World identity is a decoy.
    Word(reinterpret_cast<std::uintptr_t>(second) + 0x780, 456);
    Word(reinterpret_cast<std::uintptr_t>(second) + 0x784, 8);
    auto run = [&](O expected) {
        n::BuildingTarget target; n::BuildingTargetTestAccess::Bind(target, window);
        assert(target.Open(scene, {123, 8}, &Admit, nullptr) == expected);
        if (throw_select || fault_query) {
            assert(!target.Available()); const auto count = queries;
            assert(target.Open(scene, {123, 8}, &Admit, nullptr) == O::unavailable && queries == count);
            n::BuildingTargetTestAccess::DisposeQuarantine(target);
        }
        assert(!allocations);
        for (const auto& [object, count] : references) { (void)object; assert(count == 0); }
    };
    objects = {second, first}; run(O::submitted); assert(selections == 1 && dispatches == 1);
    objects = {second}; run(O::unavailable); assert(selections == 1);
    objects = {first, first}; run(O::unavailable); assert(selections == 1);
    objects = {first, second}; invalidate_query = true; run(O::stale); invalidate_query = false; live = true;
    invalidate_release = true; run(O::stale); invalidate_release = false; live = true;
    assert(selections == 1 && dispatches == 1);
    admitted = false; const auto before = queries; run(O::stale); admitted = true; assert(queries == before);
    Word(base + 0x4058, 0); run(O::stale); Word(base + 0x4058, base + 0xa3d0);
    Word(base + 0x6008, 4); run(O::stale); Word(base + 0x6008, 0);
    invalidate_select = true; run(O::uncertain); invalidate_select = false; live = true;
    assert(selections == 2 && dispatches == 1);
    reject_dispatch = true; run(O::uncertain); reject_dispatch = false;
    throw_select = true; run(O::uncertain); throw_select = false;
    fault_query = true; run(O::unavailable); fault_query = false;
    n::BuildingTarget target; n::BuildingTargetTestAccess::Bind(target, window);
    assert(target.Open(scene, {123, 42}, &Admit, nullptr) == O::invalid);
    std::thread foreign([&] { assert(target.Open(scene, {123, 8}, &Admit, nullptr) == O::unavailable); }); foreign.join();
    // Live Rooty coordinates use negative native Z. Query remains bounded around
    // the world pose, independently of the local pose or map-coordinate signs.
    objects = {first};
    auto position_case = [&](m::GroundPoint point, m::GroundPoint minimum, m::GroundPoint maximum) {
        std::memcpy(memory + 0x6020, &point, sizeof(point));
        expected_minimum = minimum; expected_maximum = maximum;
        const auto before_queries = queries, before_selections = selections;
        run(O::submitted);
        assert(queries == before_queries + 1 && selections == before_selections + 1);
    };
    position_case({79332.4453125f, 424.59521484375f, -52546.484375f},
        {78308.4453125f, -2000, -53570.484375f}, {80356.4453125f, 20000, -51522.484375f});
    position_case({0, 40, 0}, {0, -2000, -1024}, {1024, 20000, 0});
    position_case({200000, 40, -200000}, {198976, -2000, -200000}, {200000, 20000, -198976});
    for (const auto point : {m::GroundPoint{2000, 40, 1}, m::GroundPoint{2000, 40, -200001},
            m::GroundPoint{-1, 40, -3000}, m::GroundPoint{200001, 40, -3000},
            m::GroundPoint{2000, 40, std::numeric_limits<float>::quiet_NaN()},
            m::GroundPoint{2000, 40, -std::numeric_limits<float>::infinity()}}) {
        std::memcpy(memory + 0x6020, &point, sizeof(point));
        const auto before_queries = queries, before_selections = selections;
        run(O::stale);
        assert(queries == before_queries && selections == before_selections);
    }
    std::memcpy(memory + 0x6020, &world, sizeof(world));
    expected_minimum = {976, -2000, -4024}; expected_maximum = {3024, 20000, -1976};
    auto* npc = memory + 0xa000;
    Word(reinterpret_cast<std::uintptr_t>(npc), base + 0x114165c);
    Word(reinterpret_cast<std::uintptr_t>(npc) + 0x18, 321);
    Word(reinterpret_cast<std::uintptr_t>(npc) + 0x1c, 42);
    Word(reinterpret_cast<std::uintptr_t>(npc) + 0x780, 999); // Building offset is never used for an NPC.
    const auto old_selections = selections, old_dispatches = dispatches;
    auto warehouse = [&](O expected) {
        n::BuildingTarget t; n::BuildingTargetTestAccess::Bind(t, window);
        assert(t.OpenWarehouse(scene, {321, 42}, &Admit, nullptr) == expected);
        if (throw_open) {
            assert(!t.Available() && references[npc] == 1); // Fault quarantines the held reference.
            assert(t.OpenWarehouse(scene, {321, 42}, &Admit, nullptr) == O::unavailable);
            n::BuildingTargetTestAccess::DisposeQuarantine(t);
        }
        assert(!allocations && selections == old_selections && dispatches == old_dispatches);
        for (const auto& [object, count] : references) { (void)object; assert(count == 0); }
    };
    objects = {first, npc, second}; warehouse(O::submitted);
    assert(warehouse_opens == 1 && range_checks == 1);
    objects = {first, second}; warehouse(O::unavailable); assert(range_checks == 1);
    objects = {npc, npc}; warehouse(O::unavailable); assert(range_checks == 1);
    objects = {npc};
    Word(reinterpret_cast<std::uintptr_t>(npc) + 0x1c, 37);
    warehouse(O::unavailable); assert(range_checks == 1);
    Word(reinterpret_cast<std::uintptr_t>(npc) + 0x1c, 42);
    Word(reinterpret_cast<std::uintptr_t>(npc), base + 0x1177c0c);
    warehouse(O::unavailable); assert(range_checks == 1);
    Word(reinterpret_cast<std::uintptr_t>(npc), base + 0x114165c);
    range_ok = false; warehouse(O::unavailable); range_ok = true;
    assert(warehouse_opens == 1 && range_checks == 2);
    invalidate_range = true; warehouse(O::stale); invalidate_range = false; admitted = true;
    assert(warehouse_opens == 1);
    invalidate_query = true; warehouse(O::stale); invalidate_query = false; live = true;
    assert(warehouse_opens == 1);
    admitted = false; warehouse(O::stale); admitted = true;
    throw_open = true; warehouse(O::uncertain); throw_open = false;
    assert(warehouse_opens == 2);
    assert(target.OpenWarehouse(scene, {321, 37}, &Admit, nullptr) == O::invalid);
    std::thread wrong_thread([&] { assert(target.OpenWarehouse(scene, {321, 42}, &Admit, nullptr) == O::unavailable); });
    wrong_thread.join();
    assert(DestroyWindow(window)); assert(VirtualFree(memory, 0, MEM_RELEASE));
}
