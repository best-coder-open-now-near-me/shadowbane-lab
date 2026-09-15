#include "building_native_target.h"
#include "movement_native_image.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace wonderbane::extension::vendor_navigation {
namespace {
template<class T> bool Read(std::uintptr_t at, T& out) noexcept {
    if (at < 0x10000 || at > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(at), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
using O = vendor::wire::Outcome;
}
bool BuildingTarget::Owner() const noexcept {
    DWORD process = 0;
    return thread_ && GetCurrentThreadId() == thread_
        && GetWindowThreadProcessId(window_, &process) == thread_ && process == GetCurrentProcessId();
}
bool BuildingTarget::Bind(HWND window) noexcept {
    if (base_ || faulted_) { return false; }
    window_ = window; thread_ = GetCurrentThreadId();
    if (!Owner() || !movement::VerifyNativeMovementImage(base_)) { base_ = 0; return false; }
    calls_.construct = reinterpret_cast<decltype(calls_.construct)>(base_ + 0x2140b0);
    calls_.query = reinterpret_cast<decltype(calls_.query)>(base_ + 0x20e970);
    calls_.release = reinterpret_cast<decltype(calls_.release)>(base_ + 0x89bd0);
    calls_.pool_return = reinterpret_cast<decltype(calls_.pool_return)>(base_ + 0x40270);
    calls_.select = reinterpret_cast<decltype(calls_.select)>(base_ + 0x498730);
    calls_.dispatch = reinterpret_cast<decltype(calls_.dispatch)>(base_ + 0x7ca9c0);
    return true;
}
bool BuildingTarget::Current(const movement::NativeScene& scene, Admission admit, void* context) const noexcept {
    return Owner() && movement::NativeMovementLifetimeCurrent(scene) && admit && admit(context);
}
bool BuildingTarget::Position(const movement::NativeScene& scene, movement::GroundPoint& point) const noexcept {
    std::uintptr_t component = 0, pose = 0, parent = 0, table = 0, getter = 0;
    return Read(scene.actor, table) && Read(table + 0x58, getter) && getter == base_ + 0xa3d0
        && Read(scene.actor + 0x4b0, component) && Read(component, pose)
        && Read(pose + 8, parent) && parent == scene.parent && Read(pose + 0x20, point)
        && std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z)
        && point.x >= 0 && point.x <= 200000 && point.z >= 0 && point.z <= 200000
        && point.y >= -2000 && point.y <= 20000;
}
bool BuildingTarget::KeyOf(void* value, Key& key) const noexcept {
    key = {};
    if (!value) { return true; }
    const auto object = reinterpret_cast<std::uintptr_t>(value);
    std::uintptr_t table = 0;
    if (!Read(object, table)) { return false; }
    if (table != base_ + 0x114381c && table != base_ + 0x115ae64
        && table != base_ + 0x115b0a8 && table != base_ + 0x115b2ec && table != base_ + 0x1177c0c) { return true; }
    // The management key is separate from the world-object key at +0x18.
    return Read(object + 0x780, key);
}
bool BuildingTarget::Match(void* value, Key expected) const noexcept {
    Key key{}; return KeyOf(value, key) && key == expected;
}
void BuildingTarget::Clear() {
    if (list_.sentinel) {
        auto* node = list_.sentinel->next;
        std::size_t count = 0;
        while (node != list_.sentinel) {
            if (++count > 8192) { faulted_ = true; return; }
            auto* next = node->next;
            calls_.release(&node->object, nullptr);
            calls_.pool_return(node, sizeof(Node)); node = next;
        }
        calls_.pool_return(list_.sentinel, sizeof(Node)); list_.sentinel = nullptr;
    }
    if (held_) { calls_.release(&held_, nullptr); }
}
O BuildingTarget::Run(const movement::NativeScene& scene, Key key, Admission admit, void* context) {
    movement::GroundPoint origin{};
    if (!Current(scene, admit, context) || !Position(scene, origin)) { return O::stale; }
    unsigned char allocator = 0;
    calls_.construct(&list_, &allocator);
    // Loaded nearby structures only. Never claim city completeness or path access.
    const movement::GroundPoint minimum{(std::max)(0.0f, origin.x - 1024), -2000,
        (std::max)(0.0f, origin.z - 1024)};
    const movement::GroundPoint maximum{(std::min)(200000.0f, origin.x + 1024), 20000,
        (std::min)(200000.0f, origin.z + 1024)};
    if (!Current(scene, admit, context)) { Clear(); return O::stale; }
    // The ordinary query acquires the native world lock and retains each result.
    // No extension collection lease is held across this callback or its cleanup.
    calls_.query(reinterpret_cast<void*>(scene.world), &minimum, &maximum, &list_);
    if (!list_.sentinel) { faulted_ = true; return O::unavailable; }
    auto* previous = list_.sentinel; std::size_t count = 0, matches = 0;
    for (auto* node = list_.sentinel->next; node != list_.sentinel; node = node->next) {
        if (++count > 8192 || node->previous != previous) { faulted_ = true; return O::unavailable; }
        Key found{};
        if (!KeyOf(node->object, found)) { Clear(); return O::unavailable; }
        if (found == key) {
            if (++matches == 1) { held_ = node->object; node->object = nullptr; }
        }
        previous = node;
    }
    if (list_.sentinel->previous != previous) { faulted_ = true; return O::unavailable; }
    // Release all other query results before the final admission boundary.
    auto* target = held_; held_ = nullptr; Clear(); held_ = target;
    if (faulted_) { return O::unavailable; }
    if (matches != 1) { Clear(); return O::unavailable; }
    if (!Current(scene, admit, context) || !Match(held_, key)) { Clear(); return O::stale; }
    // The cdecl setter consumes this owned argument, including exception cleanup.
    // Detach before calling; never retry a release after uncertain native entry.
    target = held_; held_ = nullptr; entered_ = true;
    calls_.select(target);
    std::uintptr_t selected = 0;
    if (!Current(scene, admit, context) || !Read(base_ + 0x16a2da4, selected)
        || selected != reinterpret_cast<std::uintptr_t>(target) || !Match(target, key)) { return O::uncertain; }
    const std::array<std::uint32_t, 9> action{0x57c};
    return calls_.dispatch(action.data(), reinterpret_cast<void*>(scene.window)) ? O::submitted : O::uncertain;
}
O BuildingTarget::RunCxx(const movement::NativeScene& scene, Key key, Admission admit, void* context) noexcept {
    try { return Run(scene, key, admit, context); }
    catch (...) { faulted_ = true; return entered_ ? O::uncertain : O::unavailable; }
}
O BuildingTarget::Guarded(const movement::NativeScene& scene, Key key, Admission admit, void* context) noexcept {
    __try { return RunCxx(scene, key, admit, context); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return entered_ ? O::uncertain : O::unavailable; }
}
O BuildingTarget::Open(const movement::NativeScene& scene, Key key, Admission admit, void* context) noexcept {
    if (!Available() || !Owner() || running_ || list_.sentinel || held_) { return O::unavailable; }
    if (!key[0] || key[1] != 8 || !admit) { return O::invalid; }
    entered_ = false; running_ = true;
    const auto outcome = Guarded(scene, key, admit, context);
    running_ = false;
    return outcome;
}
}
