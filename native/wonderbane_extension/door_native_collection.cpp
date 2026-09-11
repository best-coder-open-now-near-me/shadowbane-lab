#include "door_native_collection.h"
#include "movement_native_image.h"
#include <cmath>
#include <cstring>
namespace wonderbane::extension::movement {
namespace {
template<class T> bool Read(std::uintptr_t address, T& out) noexcept {
    if (address < 0x10000 || address > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(address), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Structure(std::uintptr_t base, std::uintptr_t object) noexcept {
    std::uintptr_t table = 0;
    if (!Read(object, table)) { return false; }
    return table == base + 0x114381c || table == base + 0x115ae64
        || table == base + 0x115b0a8 || table == base + 0x115b2ec || table == base + 0x1177c0c;
}
}
bool NativeDoorCollection::Owner() const noexcept {
    DWORD process = 0;
    return thread_ && GetCurrentThreadId() == thread_
        && GetWindowThreadProcessId(window_, &process) == thread_ && process == GetCurrentProcessId();
}
bool NativeDoorCollection::Bind(HWND window) noexcept {
    if (base_ || faulted_) { return false; }
    window_ = window; thread_ = GetCurrentThreadId();
    if (!Owner() || !VerifyNativeMovementImage(base_)) { base_ = 0; return false; }
    calls_.construct = reinterpret_cast<decltype(calls_.construct)>(base_ + 0x2140b0);
    calls_.query = reinterpret_cast<decltype(calls_.query)>(base_ + 0x20e970);
    calls_.retain = reinterpret_cast<decltype(calls_.retain)>(base_ + 0x89ba0);
    calls_.release = reinterpret_cast<decltype(calls_.release)>(base_ + 0x89bd0);
    calls_.pool_return = reinterpret_cast<decltype(calls_.pool_return)>(base_ + 0x40270);
    return true;
}
void NativeDoorCollection::ClearList() {
    if (!list_.sentinel) { return; }
    // This list is private native query output. Its retained values are consumed
    // only here or transferred to structures_, never written back to the world.
    auto* node = list_.sentinel->next;
    while (node != list_.sentinel) {
        auto* next = node->next;
        calls_.release(&node->object, nullptr);
        calls_.pool_return(node, sizeof(Node)); node = next;
    }
    calls_.pool_return(list_.sentinel, sizeof(Node)); list_.sentinel = nullptr;
}
void NativeDoorCollection::RunClear() {
    valid_ = false; generation_ = 0;
    ClearList();
    for (std::size_t i = 0; i < door_count_; ++i) { calls_.release(&doors_[i].object, nullptr); doors_[i] = {}; }
    door_count_ = 0;
    for (std::size_t i = 0; i < structure_count_; ++i) { calls_.release(&structures_[i], nullptr); }
    structure_count_ = 0;
}
bool NativeDoorCollection::ClearCxx() noexcept {
    try { RunClear(); return true; } catch (...) { faulted_ = true; return false; }
}
bool NativeDoorCollection::ClearGuarded() noexcept {
    __try { return ClearCxx(); } __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeDoorCollection::Clear() noexcept {
    if (!Available() || !Owner()) { return false; }
    return ClearGuarded();
}
bool NativeDoorCollection::RunAcquire(const NativeScene& scene, GroundPoint origin) {
    if (!BeginNativeDoorCollectionRead(scene, lease_)) { return false; }
    lease_.Reset();
    unsigned char allocator = 0;
    calls_.construct(&list_, &allocator);
    const GroundPoint minimum{origin.x - DoorRanking::range, origin.y - DoorRanking::vertical_range, origin.z - DoorRanking::range};
    const GroundPoint maximum{origin.x + DoorRanking::range, origin.y + DoorRanking::vertical_range, origin.z + DoorRanking::range};
    // The native query holds the native world lock while retaining its result
    // objects. Never call this from inside the extension acquisition lease.
    calls_.query(reinterpret_cast<void*>(scene.world), &minimum, &maximum, &list_);
    if (!NativeMovementLifetimeCurrent(scene) || !list_.sentinel) { return false; }
    std::size_t visited = 0;
    for (auto* node = list_.sentinel->next; node != list_.sentinel; node = node->next) {
        if (++visited > 8192) { faulted_ = true; return false; }
        if (!node->object || !Structure(base_, reinterpret_cast<std::uintptr_t>(node->object))) { continue; }
        if (structure_count_ == structures_.size()) { return false; }
        structures_[structure_count_++] = node->object;
        node->object = nullptr; // transfer this private output reference
    }
    ClearList(); // Native releases may callback; the extension lease is not held.
    if (!ReadDoorsGuarded(scene)) { return false; }
    return NativeDoorCollectionCurrent(scene, generation_);
}
bool NativeDoorCollection::ReadDoorsGuarded(const NativeScene& scene) {
    // Native SEH exceptions do not necessarily unwind C++ automatic objects.
    // Always drain this reader even when an unexpected native retain faults.
    __try { return ReadDoors(scene); }
    __finally { lease_.Reset(); }
}
bool NativeDoorCollection::ReadDoors(const NativeScene& scene) {
    if (!BeginNativeDoorCollectionRead(scene, lease_)) { return false; }
    generation_ = lease_.generation;
    for (std::size_t i = 0; i < structure_count_; ++i) {
        const auto object = reinterpret_cast<std::uintptr_t>(structures_[i]);
        std::uintptr_t vector = 0;
        std::array<std::uint32_t, 2> structure_identity{};
        if (!Read(object + 0x18, structure_identity) || !Read(object + 0x748, vector)) { return false; }
        if (!vector) { continue; }
        struct Vector { std::uintptr_t begin, end, capacity; } pointers{};
        if (!Read(vector, pointers) || pointers.begin > pointers.end || pointers.end > pointers.capacity
            || ((pointers.begin | pointers.end | pointers.capacity) & 3)
            || (pointers.end - pointers.begin) / 4 > doors_.size() - door_count_) { return false; }
        for (auto at = pointers.begin; at != pointers.end; at += 4) {
            std::uintptr_t door = 0, table = 0;
            if (!Read(at, door) || !door || !Read(door, table) || table != base_ + 0x1143f18) { return false; }
            DoorIdentity identity{};
            std::array<std::uint32_t, 2> parent{}, key{};
            if (!Read(door + 0x5f0, parent) || !Read(door + 0x600, key) || parent != structure_identity) { return false; }
            identity = {parent[0], parent[1], key[0], key[1]};
            for (std::size_t previous = 0; previous < door_count_; ++previous) {
                if (doors_[previous].identity == identity) { return false; }
            }
            auto& held = doors_[door_count_];
            held = {reinterpret_cast<void*>(door), structures_[i], identity};
            // The authenticated ArcObj retain path is an atomic increment only.
            // No releases, native queries, or other callbacks occur in this lease.
            calls_.retain(&held.object); ++door_count_;
        }
    }
    return true;
}
bool NativeDoorCollection::AcquireCxx(const NativeScene& scene, GroundPoint origin) noexcept {
    try { return RunAcquire(scene, origin); } catch (...) { faulted_ = true; return false; }
}
bool NativeDoorCollection::AcquireGuarded(const NativeScene& scene, GroundPoint origin) noexcept {
    __try { return AcquireCxx(scene, origin); } __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeDoorCollection::Acquire(const NativeScene& scene, GroundPoint origin) noexcept {
    if (!Available() || !Owner()) { return false; }
    if (!Clear()) { return false; }
    if (!std::isfinite(origin.x) || !std::isfinite(origin.y) || !std::isfinite(origin.z)) { return false; }
    valid_ = AcquireGuarded(scene, origin);
    if (!valid_ && !faulted_) { (void)Clear(); }
    return valid_;
}
}
