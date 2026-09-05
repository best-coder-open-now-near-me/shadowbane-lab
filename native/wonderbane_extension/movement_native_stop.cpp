#include "movement_native_stop.h"
#include "movement_native_image.h"
#include <cmath>
#include <cstring>
namespace wonderbane::extension::movement {
namespace {
template<class T> bool Read(std::uintptr_t address, T& output) noexcept {
    if (address < 0x10000 || address > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&output, reinterpret_cast<const void*>(address), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
template<class T> bool Write(std::uintptr_t address, const T& value) noexcept {
    if (address < 0x10000 || address > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Finite(GroundPoint p) noexcept { return std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z); }
}
bool NativeStop::Bind(HWND window) noexcept {
    if (bound_ || executing_ || held_actor_ || message_) { return false; }
    DWORD pid = 0;
    const auto thread = GetWindowThreadProcessId(window, &pid);
    if (!thread || pid != GetCurrentProcessId() || !VerifyNativeMovementImage(base_)) { return false; }
    window_ = window; thread_ = thread;
    calls_.retain = reinterpret_cast<decltype(calls_.retain)>(base_ + 0x7d700);
    calls_.release = reinterpret_cast<decltype(calls_.release)>(base_ + 0x7d740);
    calls_.clear_actions = reinterpret_cast<decltype(calls_.clear_actions)>(base_ + 0x1faf90);
    calls_.find = reinterpret_cast<decltype(calls_.find)>(base_ + 0x21b7b0);
    calls_.detach = reinterpret_cast<decltype(calls_.detach)>(base_ + 0x8edd0);
    calls_.destroy_identity = reinterpret_cast<decltype(calls_.destroy_identity)>(base_ + 0x1119d0);
    calls_.pool_return = reinterpret_cast<decltype(calls_.pool_return)>(base_ + 0x40270);
    calls_.erase_path = reinterpret_cast<decltype(calls_.erase_path)>(base_ + 0x784420);
    calls_.clear_continuation = reinterpret_cast<decltype(calls_.clear_continuation)>(base_ + 0x63a30);
    calls_.position = reinterpret_cast<decltype(calls_.position)>(base_ + 0xd5680);
    calls_.destination = reinterpret_cast<decltype(calls_.destination)>(base_ + 0xccd90);
    calls_.clear_waypoint = reinterpret_cast<decltype(calls_.clear_waypoint)>(base_ + 0x79fc50);
    calls_.state = reinterpret_cast<decltype(calls_.state)>(base_ + 0x5f8c0);
    calls_.send = reinterpret_cast<decltype(calls_.send)>(base_ + 0x7f4da0);
    bound_ = true; return true;
}
bool NativeStop::BeginUpdate(void* native_window) noexcept {
    DWORD pid = 0; std::uintptr_t actual = 0;
    if (!Available() || in_update_ || executing_ || GetCurrentThreadId() != thread_
        || GetWindowThreadProcessId(window_, &pid) != thread_ || pid != GetCurrentProcessId()
        || !Read(base_ + 0x16a7bfc, actual) || actual != reinterpret_cast<std::uintptr_t>(native_window)) { return false; }
    in_update_ = true; return true;
}
void NativeStop::EndUpdate() noexcept { if (!executing_) { in_update_ = false; } }
bool NativeStop::Capture(const Grant& grant) noexcept {
    Target target{}; target.grant = grant;
    if (!Read(base_ + 0x16a2d98, target.actor) || !Read(base_ + 0x1389028, target.world)
        || !Read(base_ + 0x16a7bfc, target.window) || !target.actor || !target.world || !target.window
        || !Read(target.actor + 0x18, target.identity) || !Current(target)) { return false; }
    target_ = target; captured_ = true; return true;
}
bool NativeStop::Current(const Target& target) const noexcept {
    DWORD pid = 0;
    if (!in_update_ || !controls_.AuthorizesNativeStop(target.grant) || GetCurrentThreadId() != thread_
        || GetWindowThreadProcessId(window_, &pid) != thread_ || pid != GetCurrentProcessId()) { return false; }
    std::uintptr_t actor = 0, world = 0, window = 0; std::uint32_t mode = 0; Identity identity{};
    return Read(base_ + 0x16a2d98, actor) && actor == target.actor
        && Read(base_ + 0x1389028, world) && world == target.world
        && Read(base_ + 0x16a7bfc, window) && window == target.window
        && Read(window + 0x64, mode) && mode == 2
        && Read(actor + 0x18, identity) && identity == target.identity;
}
void NativeStop::SceneRetired(std::uint64_t scene) noexcept {
    if (captured_ && target_.grant.scene == scene) { captured_ = false; }
    // Native resources with uncertain exception ownership remain process-pinned.
}
bool NativeStop::CancelQueued(const Target& target) {
    if (!Current(target)) { return false; }
    // These are native intent fields used by the game's combat-close preference
    // and temporary follow path, not position, speed, restriction or input flags.
    // The ordinary UI toggle cannot retire both. Never restore them on release.
    if (!Write(target.actor + 0xc1c, std::uint16_t{0})) { return false; }
    calls_.clear_actions(reinterpret_cast<void*>(target.world), &target.identity);
    if (!Current(target)) { return false; }
    auto* map = reinterpret_cast<Map*>(target.world + 0xe8);
    Map snapshot{};
    if (!Read(reinterpret_cast<std::uintptr_t>(map), snapshot) || !snapshot.sentinel || snapshot.size > 1048576) {
        return false;
    }
    Node* found = nullptr;
    calls_.find(map, &found, &target.identity);
    if (!Current(target) || !found) { return false; }
    if (found != snapshot.sentinel) {
        Identity identity{};
        if (!snapshot.size || !Read(reinterpret_cast<std::uintptr_t>(found) + 16, identity)
            || identity != target.identity) { return false; }
        auto* removed = calls_.detach(found, &snapshot.sentinel->parent,
            &snapshot.sentinel->left, &snapshot.sentinel->right);
        if (removed != found) { faulted_ = true; return false; }
        calls_.destroy_identity(&removed->identity);
        calls_.pool_return(removed, sizeof(Node));
        --map->size;
    }
    if (!Current(target)) { return false; }
    // Match the native pending-path cancellation block. The native update only
    // processes state zero; do not destroy an object still owned by that update.
    std::uintptr_t request = 0; std::uint32_t request_state = 0;
    if (!Read(base_ + 0x16a1c00, request)) { return false; }
    if (request) {
        if (!Read(request, request_state)) { return false; }
        if (request_state == 0 && (!Write(request + 4, std::uint8_t{0})
            || !Write(request, std::uint32_t{1}))) { return false; }
    }
    Vector path{};
    if (!Read(target.actor + 0xc10, path)) { return false; }
    const auto begin = reinterpret_cast<std::uintptr_t>(path.begin);
    const auto end = reinterpret_cast<std::uintptr_t>(path.end);
    const auto capacity = reinterpret_cast<std::uintptr_t>(path.capacity);
    if (end < begin || capacity < end || capacity - begin > 1048576 || (end - begin) % 16) { return false; }
    calls_.erase_path(reinterpret_cast<void*>(target.actor + 0xc10), path.begin, path.end);
    if (!Current(target)) { return false; }
    calls_.clear_continuation(reinterpret_cast<void*>(target.actor));
    Vector after{};
    if (!Current(target) || !Read(target.actor + 0xc10, after) || after.begin != after.end
        || after.capacity != path.capacity || !Write(target.actor + 0xc1c, std::uint16_t{0})) { return false; }
    // Native callback side effects must not turn a partial cancellation into a
    // successful stop. Both maps share the verified two-word identity/tree layout;
    // lookup reads no value payload, unlike their different erase/destructor paths.
    for (const std::uintptr_t offset : {0xb8U, 0xe8U}) {
        Map remaining{};
        if (!Read(target.world + offset, remaining) || !remaining.sentinel) { return false; }
        Node* item = nullptr;
        calls_.find(reinterpret_cast<void*>(target.world + offset), &item, &target.identity);
        if (!Current(target) || item != remaining.sentinel) { return false; }
    }
    std::uintptr_t latest = 0;
    if (!Read(base_ + 0x16a1c00, latest) || (latest && !Read(latest, request_state))) { return false; }
    if (latest && request_state == 0) {
        if (!Write(latest + 4, std::uint8_t{0}) || !Write(latest, std::uint32_t{1})) { return false; }
    }
    return true;
}
void NativeStop::ReleaseMessage() {
    if (!message_ || message_ == reinterpret_cast<void*>(~std::uintptr_t{0})) { message_ = nullptr; return; }
    auto* reference = message_; message_ = nullptr;
    const auto table = *reinterpret_cast<std::uintptr_t**>(reference);
    const auto release = reinterpret_cast<void(__thiscall*)(void*, void**)>(table[2]);
    release(reference, &reference);
}
bool NativeStop::Run(const Target& target) {
    calls_.retain(&held_actor_, reinterpret_cast<void*>(target.actor));
    bool completed = false;
    if (held_actor_ == reinterpret_cast<void*>(target.actor) && Current(target) && CancelQueued(target)) {
        GroundPoint position{};
        calls_.position(held_actor_, &position);
        if (Current(target) && Finite(position)) {
            calls_.destination(held_actor_, &position);
            if (Current(target)) {
                calls_.clear_waypoint(reinterpret_cast<void*>(target.window), 0, 0);
                std::uintptr_t state_object = 0; std::uint32_t original_state = 0;
                if (Current(target) && Read(target.actor + 0xad0, state_object)
                    && Read(state_object + 0x10, original_state)) {
                    // Only native moving state transitions to idle. In particular,
                    // do not overwrite incapacitated/dead/seated/other states.
                    if (original_state == 7) { calls_.state(held_actor_, &message_, true, 5, true); }
                    std::uint32_t resulting_state = 0;
                    completed = Current(target) && Read(state_object + 0x10, resulting_state)
                        && resulting_state == (original_state == 7 ? 5U : original_state)
                        && (original_state != 7 || (message_ && message_ != reinterpret_cast<void*>(~std::uintptr_t{0})));
                    // State/animation notification can invoke native callbacks.
                    // Retire resulting old movement work before publishing idle.
                    if (completed) {
                        completed = CancelQueued(target) && Current(target)
                            && Read(target.actor + 0xad0, state_object)
                            && Read(state_object + 0x10, resulting_state)
                            && resulting_state == (original_state == 7 ? 5U : original_state);
                    }
                    if (completed && message_) {
                        std::uintptr_t connection = 0;
                        completed = Current(target) && Read(base_ + 0x16ab88c, connection);
                        if (completed && connection) {
                            void* outgoing = message_; message_ = nullptr;
                            // Send consumes exactly this owned by-value reference.
                            // Submission is not a claim of server acknowledgement.
                            calls_.send(reinterpret_cast<void*>(base_ + 0x16ab888), outgoing);
                            completed = Current(target);
                        }
                    }
                }
            }
        }
    }
    ReleaseMessage();
    if (held_actor_) { calls_.release(&held_actor_); }
    return completed && Current(target);
}
bool NativeStop::RunCxxGuarded(const Target& target) noexcept {
    try { return Run(target); } catch (...) { faulted_ = true; return false; }
}
bool NativeStop::RunGuarded(const Target& target) noexcept {
    __try { return RunCxxGuarded(target); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeStop::Execute(const Grant& grant) noexcept {
    if (!Available() || !in_update_ || executing_ || !controls_.AuthorizesNativeStop(grant) || GetCurrentThreadId() != thread_) {
        return false;
    }
    if ((!captured_ || target_.grant != grant) && !Capture(grant)) { return false; }
    if (!Current(target_)) { return false; }
    const Target target = target_;
    executing_ = true;
    const bool complete = RunGuarded(target);
    executing_ = false;
    if (!complete && Current(target)) {
        // A partly applied native state change cannot be retried as though its
        // outgoing message had never been built/consumed. Exclude new movement.
        faulted_ = true;
    }
    return complete;
}
}
