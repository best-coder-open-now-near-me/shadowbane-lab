#include "movement_native_stop.h"
#include "movement_native_image.h"
#include "movement_native_ui.h"
#include <algorithm>
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
bool ReadParent(std::uintptr_t actor, std::uintptr_t& parent) noexcept {
    // Same indirection as the reviewed native actor parent getter. A change of
    // this frame invalidates captured local coordinates even with the same actor.
    std::uintptr_t position = 0, pose = 0;
    return Read(actor + 0x4b0, position) && Read(position, pose) && Read(pose + 8, parent);
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
    calls_.unproject = reinterpret_cast<decltype(calls_.unproject)>(base_ + 0x14ccf0);
    calls_.ray = reinterpret_cast<decltype(calls_.ray)>(base_ + 0x242d00);
    calls_.ray_cast = reinterpret_cast<decltype(calls_.ray_cast)>(base_ + 0x20daa0);
    calls_.ray_point = reinterpret_cast<decltype(calls_.ray_point)>(base_ + 0x242e10);
    calls_.release_parent = reinterpret_cast<decltype(calls_.release_parent)>(base_ + 0x8adc0);
    calls_.apply_ray = reinterpret_cast<decltype(calls_.apply_ray)>(base_ + 0x243000);
    calls_.parent = reinterpret_cast<decltype(calls_.parent)>(base_ + 0xd0530);
    calls_.ground_with_refs = reinterpret_cast<decltype(calls_.ground_with_refs)>(base_ + 0x2d2010);
    calls_.release_ground_actor = reinterpret_cast<decltype(calls_.release_ground_actor)>(base_ + 0x89bd0);
    calls_.ground_target = reinterpret_cast<decltype(calls_.ground_target)>(base_ + 0x2d1fa0);
    calls_.move = reinterpret_cast<decltype(calls_.move)>(base_ + 0x62570);
    calls_.camera = reinterpret_cast<decltype(calls_.camera)>(base_ + 0x51c210);
    require_lifetime_ = true; bound_ = true; return true;
}
bool NativeStop::BeginUpdate(void* native_window, const NativeScene& scene) noexcept {
    if (in_update_ || executing_ || GetCurrentThreadId() != thread_
        || scene.window != reinterpret_cast<std::uintptr_t>(native_window)
        || !NativeMovementLifetimeCurrent(scene)) { return false; }
    lifetime_scene_ = scene;
    if (BeginUpdate(native_window)) { return true; }
    lifetime_scene_ = {}; return false;
}
bool NativeStop::BeginOwnerStop(HWND source_window, void* native_window, const NativeScene& scene) noexcept {
    if (source_window != window_ || !BeginUpdate(native_window, scene)) { return false; }
    stop_only_ = true; return true;
}
bool NativeStop::BeginUpdate(void* native_window) noexcept {
    DWORD pid = 0; std::uintptr_t actual = 0;
    if (!Available() || in_update_ || executing_ || (require_lifetime_ && !NativeMovementLifetimeCurrent(lifetime_scene_))
        || GetCurrentThreadId() != thread_
        || GetWindowThreadProcessId(window_, &pid) != thread_ || pid != GetCurrentProcessId()
        || !Read(base_ + 0x16a7bfc, actual) || !actual || actual != reinterpret_cast<std::uintptr_t>(native_window)) { return false; }
    in_update_ = true; return true;
}
void NativeStop::EndUpdate() noexcept {
    if (!in_update_ || executing_ || GetCurrentThreadId() != thread_) { return; }
    executing_ = true;
    if (!faulted_) { (void)ClearPickGuarded(); }
    executing_ = false; in_update_ = false; lifetime_scene_ = {}; stop_only_ = false;
}
bool NativeStop::Capture(const Grant& grant) noexcept {
    Target target{}; target.grant = grant;
    if (!Read(base_ + 0x16a2d98, target.actor) || !Read(base_ + 0x1389028, target.world)
        || !Read(base_ + 0x16a7bfc, target.window) || !target.actor || !target.world || !target.window
        || !Read(target.actor + 0x18, target.identity) || !ReadParent(target.actor, target.parent) || !Current(target)) { return false; }
    target_ = target; captured_ = true; return true;
}
bool NativeStop::Current(const Target& target) const noexcept {
    return controls_.AuthorizesNativeStop(target.grant) && SceneCurrent(target);
}
bool NativeStop::SceneCurrent(const Target& target) const noexcept {
    DWORD pid = 0;
    if (require_lifetime_ && (!NativeMovementLifetimeCurrent(lifetime_scene_)
        || target.actor != lifetime_scene_.actor || target.world != lifetime_scene_.world
        || target.parent != lifetime_scene_.parent || target.identity != lifetime_scene_.identity
        || target.grant.scene != lifetime_scene_.epoch)) { return false; }
    if (!in_update_ || !target.grant.scene || controls_.Current().scene != target.grant.scene || GetCurrentThreadId() != thread_
        || GetWindowThreadProcessId(window_, &pid) != thread_ || pid != GetCurrentProcessId()) { return false; }
    std::uintptr_t actor = 0, world = 0, window = 0, parent = 0; std::uint32_t mode = 0; Identity identity{};
    return Read(base_ + 0x16a2d98, actor) && actor == target.actor
        && Read(base_ + 0x1389028, world) && world == target.world
        && Read(base_ + 0x16a7bfc, window) && window == target.window
        && Read(window + 0x64, mode) && mode == 2
        && Read(actor + 0x18, identity) && identity == target.identity
        && ReadParent(actor, parent) && parent == target.parent;
}
bool NativeStop::RequestCurrent(const Target& target) const noexcept {
    std::uintptr_t request = 0;
    return Current(target) && Read(base_ + 0x16a1c00, request) && request == target.request;
}
bool NativeStop::ClearPickCxxGuarded() noexcept {
    pick_valid_ = false;
    try {
        if (ray_owned_) {
            calls_.release_parent(&ray_.parent, nullptr);
            calls_.release(&ray_.actor);
            ray_owned_ = false; ray_ = {};
        }
        return true;
    } catch (...) { faulted_ = true; return false; }
}
bool NativeStop::ClearPickGuarded() noexcept {
    __try { return ClearPickCxxGuarded(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeStop::PickGround(int x, int y, GroundPoint& output) noexcept {
    output = {};
    if (stop_only_ || !Available() || !in_update_ || executing_ || !controls_.Ready() || GetCurrentThreadId() != thread_) { return false; }
    executing_ = true;
    const bool result = ClearPickGuarded() && PickGuarded(x, y, output);
    executing_ = false;
    return result;
}
bool NativeStop::RunPick(int x, int y, GroundPoint& output) {
    RECT bounds{};
    if (!GetClientRect(window_, &bounds) || x < 0 || y < 0 || x >= bounds.right || y >= bounds.bottom) { return false; }
    Target target{}; target.grant = controls_.Current();
    if (!Read(base_ + 0x16a2d98, target.actor) || !Read(base_ + 0x1389028, target.world)
        || !Read(base_ + 0x16a7bfc, target.window) || !target.actor || !target.world || !target.window
        || !Read(target.actor + 0x18, target.identity) || !ReadParent(target.actor, target.parent) || !SceneCurrent(target)) { return false; }
    GroundPoint origin{}, screen{};
    if (!Read(base_ + 0x16a2c34, origin) || !Finite(origin)) { return false; }
    POINT native_point{x, y};
    if (require_lifetime_ && NativeClientPoint(base_, target.window, window_, {x, y}, native_point) != NativePointResult::valid) { return false; }
    calls_.unproject(&screen, native_point.x, native_point.y, 0.0F);
    if (!SceneCurrent(target) || !Finite(screen)) { return false; }
    GroundPoint direction{screen.x - origin.x, screen.y - origin.y, screen.z - origin.z};
    const float length = std::hypot(direction.x, direction.y, direction.z);
    if (!std::isfinite(length) || length <= 0) { return false; }
    direction.x /= length; direction.y /= length; direction.z /= length;
    ray_owned_ = true;
    calls_.ray(&ray_, reinterpret_cast<void*>(target.actor), &origin, &direction, false);
    if (!SceneCurrent(target) || ray_.actor != reinterpret_cast<void*>(target.actor)) { return false; }
    if (!calls_.ray_cast(reinterpret_cast<void*>(target.world), &ray_) || !SceneCurrent(target)
        || !std::isfinite(ray_.distance) || ray_.distance < 0) { return false; }
    // This native helper locks and reads the actor/parent transformation and
    // converts the world hit into the player's native parent-local coordinates.
    calls_.ray_point(&ray_, &pick_point_);
    if (!SceneCurrent(target) || !Finite(pick_point_)) { return false; }
    pick_target_ = target; pick_valid_ = true; output = pick_point_; return true;
}
bool NativeStop::PickCxxGuarded(int x, int y, GroundPoint& output) noexcept {
    try { return RunPick(x, y, output); } catch (...) { faulted_ = true; return false; }
}
bool NativeStop::PickGuarded(int x, int y, GroundPoint& output) noexcept {
    __try { return PickCxxGuarded(x, y, output); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeStop::CameraBasis(Vector2& forward, Vector2& right) noexcept {
    forward = {}; right = {};
    if (stop_only_ || !Available() || !in_update_ || executing_ || !controls_.Ready() || GetCurrentThreadId() != thread_) { return false; }
    executing_ = true;
    bool result = ClearPickGuarded() && BasisGuarded(forward, right);
    if (!faulted_) { result = ClearPickGuarded() && result; }
    result = result && SceneCurrent(pick_target_);
    if (!result) { forward = {}; right = {}; }
    executing_ = false; return result;
}
bool NativeStop::RunBasis(Vector2& forward, Vector2& right) {
    RECT bounds{};
    if (!GetClientRect(window_, &bounds) || bounds.right < 2 || bounds.bottom < 2) { return false; }
    Target target{}; target.grant = controls_.Current();
    if (!Read(base_ + 0x16a2d98, target.actor) || !Read(base_ + 0x1389028, target.world)
        || !Read(base_ + 0x16a7bfc, target.window) || !target.actor || !target.world || !target.window
        || !Read(target.actor + 0x18, target.identity) || !ReadParent(target.actor, target.parent) || !SceneCurrent(target)) { return false; }
    pick_target_ = target;
    GroundPoint origin{}, center{}, side{}, local_origin{}, local_center{}, local_side{};
    if (!Read(base_ + 0x16a2c34, origin) || !Finite(origin)) { return false; }
    const int x = bounds.right / 2, y = bounds.bottom / 2;
    const int side_x = std::min(bounds.right - 1, x + std::max(1L, bounds.right / 4));
    POINT native_center{x, y}, native_side{side_x, y};
    if (require_lifetime_ && (NativeClientPoint(base_, target.window, window_, {x, y}, native_center) != NativePointResult::valid
        || NativeClientPoint(base_, target.window, window_, {side_x, y}, native_side) != NativePointResult::valid)) { return false; }
    calls_.unproject(&center, native_center.x, native_center.y, 0.0F);
    if (!SceneCurrent(target) || !Finite(center)) { return false; }
    calls_.unproject(&side, native_side.x, native_side.y, 0.0F);
    if (!SceneCurrent(target) || !Finite(side)) { return false; }
    // Use the current native view's rays, including its orbit/parent offset.
    // No cached/invented view matrix or guessed yaw-axis convention is needed.
    // A zero-distance native ray converts each owned scratch origin through the
    // same locked inverse-parent helper as terrain picking; it is not a ground pick.
    GroundPoint zero{}; ray_owned_ = true;
    calls_.ray(&ray_, reinterpret_cast<void*>(target.actor), &origin, &zero, false);
    if (!SceneCurrent(target) || ray_.actor != reinterpret_cast<void*>(target.actor)) { return false; }
    ray_.distance = 0;
    calls_.ray_point(&ray_, &local_origin);
    if (!SceneCurrent(target) || !Finite(local_origin)) { return false; }
    ray_.origin = center; calls_.ray_point(&ray_, &local_center);
    if (!SceneCurrent(target) || !Finite(local_center)) { return false; }
    ray_.origin = side; calls_.ray_point(&ray_, &local_side);
    if (!SceneCurrent(target) || !Finite(local_side)) { return false; }
    const Vector2 along{local_center.x - local_origin.x, local_center.z - local_origin.z};
    const Vector2 across{local_side.x - local_center.x, local_side.z - local_center.z};
    const float length = std::hypot(along.x, along.y);
    if (!std::isfinite(length) || length <= 0.000001F) { return false; }
    forward = {along.x / length, along.y / length};
    right = {-forward.y, forward.x};
    const float sign = right.x * across.x + right.y * across.y;
    if (!std::isfinite(sign) || std::abs(sign) <= 0.000001F) { return false; }
    if (sign < 0) { right.x = -right.x; right.y = -right.y; }
    return true;
}
bool NativeStop::BasisCxxGuarded(Vector2& forward, Vector2& right) noexcept {
    try { return RunBasis(forward, right); } catch (...) { faulted_ = true; return false; }
}
bool NativeStop::BasisGuarded(Vector2& forward, Vector2& right) noexcept {
    __try { return BasisCxxGuarded(forward, right); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeStop::MoveToPick(const Grant& grant, GroundPoint point) noexcept {
    if (stop_only_ || !Available() || !in_update_ || executing_ || !controls_.Ready() || GetCurrentThreadId() != thread_
        || !pick_valid_ || !ray_owned_ || !Finite(point) || point.x != pick_point_.x || point.y != pick_point_.y
        || point.z != pick_point_.z || grant.owner == Owner::none || grant != controls_.Current()
        || grant.scene != pick_target_.grant.scene || !SceneCurrent(pick_target_)) { return false; }
    Target target = pick_target_; target.grant = grant;
    // Pin failed-command cleanup before entering marker or movement callbacks.
    if (steering_captured_ && steering_target_.grant == grant && !MovementCurrent(steering_target_)) { return false; }
    if (!steering_captured_ || steering_target_.grant != grant) { drag_submitted_ = drag_deferred_ = false; }
    steering_target_ = target; steering_captured_ = true;
    executing_ = true;
    const bool result = PickMoveGuarded(target);
    executing_ = false;
    return result;
}
bool NativeStop::RunPickMove(const Target& target) {
    std::uintptr_t marker = 0, connection = 0;
    if (!MovementCurrent(target) || !Read(target.window + 0x120, marker) || !marker
        || !Read(base_ + 0x16ab88c, connection) || !connection) { return false; }
    if (drag_submitted_) {
        std::uintptr_t request = 0, state_object = 0; std::uint32_t request_state = 1, state = 0;
        if (!Read(base_ + 0x16a1c00, request) || (request && !Read(request, request_state))) { return false; }
        // Keep only the latest pointer pick while the native solver owns its
        // request; the next owning update applies it after native completion.
        if (request && request_state == 0) { return true; }
        if (drag_deferred_) {
            Map map{}; Node* found = nullptr;
            if (!Read(target.world + 0xb8, map) || !map.sentinel) { return false; }
            calls_.find(reinterpret_cast<void*>(target.world + 0xb8), &found, &target.identity);
            if (!MovementCurrent(target) || !found) { return false; }
            if (found != map.sentinel) { return true; }
        }
        if (!Read(target.actor + 0xad0, state_object) || !Read(state_object + 0x10, state)) { return false; }
        if (state == 7 && pick_point_.x == drag_point_.x && pick_point_.y == drag_point_.y && pick_point_.z == drag_point_.z) {
            return true;
        }
    }
    calls_.retain(&held_actor_, reinterpret_cast<void*>(target.actor));
    bool completed = false;
    if (held_actor_ == reinterpret_cast<void*>(target.actor) && MovementCurrent(target)) {
        calls_.retain(&held_marker_, reinterpret_cast<void*>(marker));
        std::uintptr_t current_marker = 0;
        if (held_marker_ == reinterpret_cast<void*>(marker) && MovementCurrent(target)
            && Read(target.window + 0x120, current_marker) && current_marker == marker) {
            // Native hit application updates the game's destination marker and
            // its terrain/parent attachment, never the controlled actor pose.
            calls_.apply_ray(&ray_, held_marker_, true);
            if (MovementCurrent(target) && Read(target.window + 0x120, current_marker) && current_marker == marker) {
                void* parent = calls_.parent(held_marker_);
                if (MovementCurrent(target)) {
                    ground_owned_ = true;
                    calls_.ground_with_refs(&ground_, pick_point_, held_marker_, parent);
                    if (MovementCurrent(target)) {
                        calls_.move(held_actor_, &message_, &ground_, true, true, false, nullptr, false);
                        completed = MovementCurrent(target);
                        drag_deferred_ = !message_;
                    }
                }
            }
        }
    }
    if (ground_owned_) {
        calls_.release_parent(&ground_.parent, nullptr);
        calls_.release_ground_actor(&ground_.actor, nullptr);
        ground_owned_ = false; ground_ = {};
    }
    // Native target reference destruction can call back. Never send its old
    // command after a scene/owner change during cleanup.
    if (completed && MovementCurrent(target) && message_ && message_ != reinterpret_cast<void*>(~std::uintptr_t{0})) {
        completed = Read(base_ + 0x16ab88c, connection) && connection != 0;
        if (completed) {
            void* outgoing = message_; message_ = nullptr;
            calls_.send(reinterpret_cast<void*>(base_ + 0x16ab888), outgoing);
        }
    }
    ReleaseMessage();
    if (held_marker_) { calls_.release(&held_marker_); }
    if (held_actor_) { calls_.release(&held_actor_); }
    // Changing between held drag and directional steering must not reuse a
    // pending-direction coalescing decision from the preceding input method.
    if (completed && MovementCurrent(target)) {
        steering_submitted_ = steering_sent_ = steering_deferred_ = false;
        drag_point_ = pick_point_; drag_submitted_ = true;
        return true;
    }
    return false;
}
bool NativeStop::PickMoveCxxGuarded(const Target& target) noexcept {
    try { return RunPickMove(target); } catch (...) { faulted_ = true; return false; }
}
bool NativeStop::PickMoveGuarded(const Target& target) noexcept {
    __try { return PickMoveCxxGuarded(target); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeStop::MovementCurrent(const Target& target) const noexcept {
    return controls_.Ready() && target.grant.owner != Owner::none && controls_.Current() == target.grant && Current(target);
}
bool NativeStop::Steer(const Grant& grant, Vector2 direction, std::uint64_t tick, bool start) noexcept {
    if (stop_only_ || !Available() || !in_update_ || executing_ || GetCurrentThreadId() != thread_
        || !controls_.Ready() || grant.owner == Owner::none || controls_.Current() != grant
        || !std::isfinite(direction.x) || !std::isfinite(direction.y)
        || std::abs(std::hypot(direction.x, direction.y) - 1.0F) > 0.001F) { return false; }
    if (!steering_captured_ || steering_target_.grant != grant) {
        Target target{}; target.grant = grant;
        if (!Read(base_ + 0x16a2d98, target.actor) || !Read(base_ + 0x1389028, target.world)
            || !Read(base_ + 0x16a7bfc, target.window) || !target.actor || !target.world || !target.window
            || !Read(target.actor + 0x18, target.identity) || !ReadParent(target.actor, target.parent) || !MovementCurrent(target)) { return false; }
        steering_target_ = target; steering_captured_ = true;
        steering_submitted_ = steering_sent_ = steering_deferred_ = false;
    }
    if (!MovementCurrent(steering_target_) || (steering_submitted_ && tick < steering_tick_)) { return false; }
    executing_ = true;
    const bool result = SteerGuarded(steering_target_, direction, tick, start);
    executing_ = false;
    return result;
}
bool NativeStop::RunSteer(const Target& target, Vector2 direction, std::uint64_t tick, bool start) {
    if (!MovementCurrent(target)) { return false; }
    std::uintptr_t connection = 0;
    if (!Read(base_ + 0x16ab88c, connection) || !connection) { return false; }
    const bool changed = !steering_submitted_ || direction.x != steering_direction_.x || direction.y != steering_direction_.y;
    if (!start && !changed) {
        // Do not restart an in-flight native path solve every input update. A
        // direction change goes through native replacement; release uses Execute.
        std::uintptr_t request = 0; std::uint32_t state = 1;
        if (!Read(base_ + 0x16a1c00, request) || (request && !Read(request, state))) { return false; }
        if (request && state == 0) { steering_tick_ = tick; return true; }
        if (steering_deferred_) {
            Map map{}; Node* found = nullptr;
            if (!Read(target.world + 0xb8, map) || !map.sentinel) { return false; }
            calls_.find(reinterpret_cast<void*>(target.world + 0xb8), &found, &target.identity);
            if (!MovementCurrent(target) || !found) { return false; }
            if (found != map.sentinel) { steering_tick_ = tick; return true; }
        }
    }
    calls_.retain(&held_actor_, reinterpret_cast<void*>(target.actor));
    bool completed = false;
    if (held_actor_ == reinterpret_cast<void*>(target.actor) && MovementCurrent(target)) {
        GroundPoint position{}; calls_.position(held_actor_, &position);
        float distance = 0;
        if (MovementCurrent(target) && Finite(position) && Read(base_ + 0x1141544, distance)
            && std::isfinite(distance) && distance > 0) {
            // Match the native continuous routine's look-ahead, not its input
            // flag writes. Native Move still owns collision, restrictions,
            // animation/deferred admission, path solving and movement speed.
            GroundTarget ground{};
            const GroundPoint wanted{position.x + direction.x * distance, position.y, position.z + direction.y * distance};
            if (Finite(wanted)) {
                calls_.ground_target(&ground, wanted);
                if (MovementCurrent(target)) {
                    const bool publish = start || !steering_sent_ || tick - steering_sent_tick_ >= 400;
                    calls_.move(held_actor_, &message_, &ground, publish, true, false, nullptr, false);
                    completed = MovementCurrent(target);
                    // Null output is legitimate native rejection/deferred work,
                    // not evidence that restrictions should be bypassed.
                    steering_deferred_ = !message_;
                    if (completed && message_ && message_ != reinterpret_cast<void*>(~std::uintptr_t{0})) {
                        completed = Read(base_ + 0x16ab88c, connection) && connection != 0;
                        if (completed) {
                            void* outgoing = message_; message_ = nullptr;
                            calls_.send(reinterpret_cast<void*>(base_ + 0x16ab888), outgoing);
                            completed = MovementCurrent(target);
                            if (completed) { steering_sent_ = true; steering_sent_tick_ = tick; }
                        }
                    }
                }
            }
        }
    }
    ReleaseMessage();
    if (held_actor_) { calls_.release(&held_actor_); }
    if (completed && MovementCurrent(target)) {
        drag_submitted_ = drag_deferred_ = false;
        steering_direction_ = direction; steering_tick_ = tick; steering_submitted_ = true; return true;
    }
    return false;
}
bool NativeStop::SteerCxxGuarded(const Target& target, Vector2 direction, std::uint64_t tick, bool start) noexcept {
    try { return RunSteer(target, direction, tick, start); } catch (...) { faulted_ = true; return false; }
}
bool NativeStop::SteerGuarded(const Target& target, Vector2 direction, std::uint64_t tick, bool start) noexcept {
    __try { return SteerCxxGuarded(target, direction, tick, start); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; return false; }
}
bool NativeStop::RotateCamera(Vector2 radians) noexcept {
    if (stop_only_ || !Available() || !controls_.CameraReady() || !in_update_ || executing_
        || GetCurrentThreadId() != thread_ || !std::isfinite(radians.x) || !std::isfinite(radians.y)) { return false; }
    Target target{}; target.grant = controls_.Current();
    if (!Read(base_ + 0x16a2d98, target.actor) || !Read(base_ + 0x1389028, target.world)
        || !Read(base_ + 0x16a7bfc, target.window) || !target.actor || !target.world || !target.window
        || !Read(target.actor + 0x18, target.identity) || !ReadParent(target.actor, target.parent) || !Current(target)) { return false; }
    executing_ = true;
    const bool result = RotateCameraGuarded(target, radians);
    executing_ = false;
    // Controls latches a camera failure independently from movement. Do not poison
    // a route's stop path or replace its captured target on camera-only input.
    return result;
}
bool NativeStop::RotateCameraGuarded(const Target& target, Vector2 radians) noexcept {
    __try {
        float yaw = 0, pitch = 0, distance = 0, half_pi = 0, margin = 0, lower = 0;
        const auto camera = base_ + 0x16a2c10;
        if (!Current(target) || !Read(camera + 0x68, yaw) || !Read(camera + 0x70, pitch)
            || !Read(camera + 0x7c, distance) || !Read(base_ + 0x1163250, half_pi)
            || !Read(base_ + 0x1163300, margin) || !Read(base_ + 0x1163254, lower)
            || !std::isfinite(yaw) || !std::isfinite(pitch) || !std::isfinite(distance)
            || half_pi <= 0 || margin < 0 || margin >= 1 || lower <= 0
            || !std::isfinite(half_pi) || !std::isfinite(margin) || !std::isfinite(lower)) { return false; }
        const float next_yaw = yaw + radians.x;
        const float next_pitch = pitch + radians.y;
        if (!std::isfinite(next_yaw) || !std::isfinite(next_pitch)) { return false; }
        // The native delta gesture accumulates mouse inertia on every invocation.
        // The native orientation setter avoids making controller sensitivity
        // depend on that event count. Match the native pitch limits, preserve
        // camera distance and inertia, and leave matrix/collision updates native.
        // false selects the sealed branch that does not dereference a camera
        // target or alter its parent-relative yaw offset.
        calls_.camera(reinterpret_cast<void*>(camera),
            std::clamp(next_pitch, -lower, half_pi - half_pi * margin), next_yaw, distance, false);
        return Current(target);
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
void NativeStop::SceneRetired(std::uint64_t scene) noexcept {
    if (pick_target_.grant.scene == scene) { pick_valid_ = false; }
    if (captured_ && target_.grant.scene == scene) { captured_ = false; }
    if (steering_captured_ && steering_target_.grant.scene == scene) { steering_captured_ = false; }
    // Native resources with uncertain exception ownership remain process-pinned.
}
bool NativeStop::CancelQueued(const Target& target) {
    if (!RequestCurrent(target)) { return false; }
    // These are native intent fields used by the game's combat-close preference
    // and temporary follow path, not position, speed, restriction or input flags.
    // The ordinary UI toggle cannot retire both. Never restore them on release.
    if (!Write(target.actor + 0xc1c, std::uint16_t{0})) { return false; }
    calls_.clear_actions(reinterpret_cast<void*>(target.world), &target.identity);
    if (!RequestCurrent(target)) { return false; }
    auto* map = reinterpret_cast<Map*>(target.world + 0xe8);
    Map snapshot{};
    if (!Read(reinterpret_cast<std::uintptr_t>(map), snapshot) || !snapshot.sentinel || snapshot.size > 1048576) {
        return false;
    }
    Node* found = nullptr;
    calls_.find(map, &found, &target.identity);
    if (!RequestCurrent(target) || !found) { return false; }
    if (found != snapshot.sentinel) {
        Identity identity{};
        if (!snapshot.size || !Read(reinterpret_cast<std::uintptr_t>(found) + 16, identity)
            || identity != target.identity) { return false; }
        auto* removed = calls_.detach(found, &snapshot.sentinel->parent,
            &snapshot.sentinel->left, &snapshot.sentinel->right);
        if (removed != found) { faulted_ = true; return false; }
        // Sealed detach/key destructor/pool return have no gameplay callback:
        // the first two are pure container/value code, the pool uses Win32
        // InterlockedExchange/Sleep only. No new command is admitted in this group.
        calls_.destroy_identity(&removed->identity);
        calls_.pool_return(removed, sizeof(Node));
        if (!RequestCurrent(target)) { return false; }
        --map->size;
    }
    if (!RequestCurrent(target)) { return false; }
    // The reviewed producer allocates this slot only for the current player;
    // the world consumer processes/applies it with that same current-player
    // global. It has no independent actor/world identity tag that we can trust.
    // Pin its exact pointer with the captured actor/world for this transaction;
    // never adopt a replacement created by a native callback.
    // Match the native pending-path cancellation block. The native update only
    // processes state zero; do not destroy an object still owned by that update.
    std::uintptr_t request = 0; std::uint32_t request_state = 0;
    if (!Read(base_ + 0x16a1c00, request) || request != target.request) { return false; }
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
    if (!RequestCurrent(target)) { return false; }
    calls_.clear_continuation(reinterpret_cast<void*>(target.actor));
    Vector after{};
    if (!RequestCurrent(target) || !Read(target.actor + 0xc10, after) || after.begin != after.end
        || after.capacity != path.capacity || !Write(target.actor + 0xc1c, std::uint16_t{0})) { return false; }
    // Native callback side effects must not turn a partial cancellation into a
    // successful stop. Both maps share the verified two-word identity/tree layout;
    // lookup reads no value payload, unlike their different erase/destructor paths.
    for (const std::uintptr_t offset : {0xb8U, 0xe8U}) {
        Map remaining{};
        if (!Read(target.world + offset, remaining) || !remaining.sentinel) { return false; }
        Node* item = nullptr;
        calls_.find(reinterpret_cast<void*>(target.world + offset), &item, &target.identity);
        if (!RequestCurrent(target) || item != remaining.sentinel) { return false; }
    }
    std::uintptr_t latest = 0;
    if (!RequestCurrent(target) || !Read(base_ + 0x16a1c00, latest)
        || latest != target.request || (latest && !Read(latest, request_state))) { return false; }
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
    if (!RequestCurrent(target)) { return false; }
    calls_.retain(&held_actor_, reinterpret_cast<void*>(target.actor));
    bool completed = false;
    if (held_actor_ == reinterpret_cast<void*>(target.actor) && RequestCurrent(target) && CancelQueued(target)) {
        GroundPoint position{};
        calls_.position(held_actor_, &position);
        if (RequestCurrent(target) && Finite(position)) {
            calls_.destination(held_actor_, &position);
            if (RequestCurrent(target)) {
                calls_.clear_waypoint(reinterpret_cast<void*>(target.window), 0, 0);
                std::uintptr_t state_object = 0; std::uint32_t original_state = 0;
                if (RequestCurrent(target) && Read(target.actor + 0xad0, state_object)
                    && Read(state_object + 0x10, original_state)) {
                    // Only native moving state transitions to idle. In particular,
                    // do not overwrite incapacitated/dead/seated/other states.
                    if (original_state == 7) { calls_.state(held_actor_, &message_, true, 5, true); }
                    std::uint32_t resulting_state = 0;
                    completed = RequestCurrent(target) && Read(state_object + 0x10, resulting_state)
                        && resulting_state == (original_state == 7 ? 5U : original_state)
                        && (original_state != 7 || (message_ && message_ != reinterpret_cast<void*>(~std::uintptr_t{0})));
                    // State/animation notification can invoke native callbacks.
                    // Retire resulting old movement work before publishing idle.
                    if (completed) {
                        completed = CancelQueued(target) && RequestCurrent(target)
                            && Read(target.actor + 0xad0, state_object)
                            && Read(state_object + 0x10, resulting_state)
                            && resulting_state == (original_state == 7 ? 5U : original_state);
                    }
                    if (completed && message_) {
                        std::uintptr_t connection = 0;
                        completed = RequestCurrent(target) && Read(base_ + 0x16ab88c, connection) && connection != 0;
                        if (completed) {
                            void* outgoing = message_; message_ = nullptr;
                            // Send consumes exactly this owned by-value reference.
                            // Submission is not a claim of server acknowledgement.
                            calls_.send(reinterpret_cast<void*>(base_ + 0x16ab888), outgoing);
                            completed = RequestCurrent(target);
                        }
                    }
                }
            }
        }
    }
    ReleaseMessage();
    if (held_actor_) { calls_.release(&held_actor_); }
    return completed && RequestCurrent(target);
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
    // A failed move can have changed the native scene inside its callbacks. Its
    // cleanup stop belongs to the actor captured for that movement, never a fresh
    // actor discovered under the still-old policy scene on return.
    if (steering_captured_ && steering_target_.grant == grant) {
        if (!Current(steering_target_)) { return false; }
        target_ = steering_target_; captured_ = true;
    } else if ((!captured_ || target_.grant != grant) && !Capture(grant)) { return false; }
    if (!Current(target_)) { return false; }
    Target target = target_;
    // A later stop in the same manual grant may retire a different request.
    // Seal once per execution, before any native call, never during cleanup.
    if (!Read(base_ + 0x16a1c00, target.request) || !RequestCurrent(target)) { return false; }
    executing_ = true;
    const bool complete = RunGuarded(target);
    executing_ = false;
    if (!complete && Current(target)) {
        // A partly applied native state change cannot be retried as though its
        // outgoing message had never been built/consumed. Exclude new movement.
        faulted_ = true;
    }
    if (complete && steering_captured_ && steering_target_.grant == grant) {
        steering_submitted_ = steering_sent_ = steering_deferred_ = false;
        drag_submitted_ = drag_deferred_ = false;
    }
    return complete;
}
}
