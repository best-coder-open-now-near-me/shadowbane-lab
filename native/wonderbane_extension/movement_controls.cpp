#include "movement_controls.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace wonderbane::extension::movement {
namespace {
bool Finite(Vector2 v) noexcept { return std::isfinite(v.x) && std::isfinite(v.y); }
bool Finite(GroundPoint v) noexcept {
    return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z);
}
float Length(Vector2 v) noexcept { return std::hypot(v.x, v.y); }
bool Nonzero(Vector2 v) noexcept { return v.x != 0 || v.y != 0; }
bool ValidTokenText(const std::array<char, 96>& text) noexcept {
    bool ended = false;
    if (text[0] == 0) { return false; }
    for (const char c : text) {
        if (c == 0) { ended = true; }
        else if (ended || c < 0x21 || c > 0x7E) { return false; }
    }
    return ended;
}
bool Basis(const Input& input) noexcept {
    if (!input.camera_basis_valid || !Finite(input.camera_forward)
        || !Finite(input.camera_right)) { return false; }
    const auto f = input.camera_forward;
    const auto r = input.camera_right;
    return std::abs(Length(f) - 1.0F) < 0.01F && std::abs(Length(r) - 1.0F) < 0.01F
        && std::abs(f.x * r.x + f.y * r.y) < 0.01F;
}
Vector2 WorldDirection(Vector2 local, const Input& input) noexcept {
    return RadialDirection({
        input.camera_right.x * local.x + input.camera_forward.x * local.y,
        input.camera_right.y * local.x + input.camera_forward.y * local.y}, 0);
}
}

bool ValidSettings(const Settings& s) noexcept {
    for (std::size_t i = 0; i < s.keys.size(); ++i) {
        if (s.keys[i] < 0x08 || s.keys[i] > 0xFE) { return false; }
        for (std::size_t j = 0; j < i; ++j) {
            if (s.keys[i] == s.keys[j]) { return false; }
        }
    }
    return s.controller_slot < 4 && std::isfinite(s.movement_dead_zone)
        && s.movement_dead_zone >= 0.05F && s.movement_dead_zone < 0.95F
        && std::isfinite(s.camera_dead_zone) && s.camera_dead_zone >= 0.05F
        && s.camera_dead_zone < 0.95F && std::isfinite(s.camera_radians_per_second)
        && s.camera_radians_per_second > 0 && s.camera_radians_per_second <= 10
        && (s.drag_button == 1 || s.drag_button == 2 || s.drag_button == 4
            || s.drag_button == 5 || s.drag_button == 6)
        && std::isfinite(s.drag_threshold_pixels)
        && s.drag_threshold_pixels >= 2 && s.drag_threshold_pixels <= 64;
}

Vector2 RadialDirection(Vector2 value, float dead_zone) noexcept {
    if (!Finite(value) || !std::isfinite(dead_zone) || dead_zone < 0 || dead_zone >= 1) {
        return {};
    }
    const float length = Length(value);
    if (!std::isfinite(length) || length <= dead_zone) { return {}; }
    return {value.x / length, value.y / length};
}
Vector2 RadialCamera(Vector2 value, float dead_zone) noexcept {
    const Vector2 direction = RadialDirection(value, dead_zone);
    if (!Nonzero(direction)) { return {}; }
    const float magnitude = (std::min(Length(value), 1.0F) - dead_zone) / (1.0F - dead_zone);
    return {direction.x * magnitude, direction.y * magnitude};
}

bool Controls::RetryStop() noexcept {
    if (!pending_stop_) { return true; }
    if (!actuator_.Stop(pending_grant_, pending_reason_)) { return false; }
    pending_stop_ = false;
    return true;
}
bool Controls::StopActive(StopReason reason) noexcept {
    if (!RetryStop()) { return false; }
    // Native click/follow intent may exist before this controller has submitted
    // a move. Admission must retire it before publishing a replacement owner.
    if (!moving_ && reason != StopReason::takeover) { return true; }
    moving_ = false;
    if (actuator_.Stop(grant_, reason)) { return true; }
    pending_grant_ = grant_;
    pending_reason_ = reason;
    pending_stop_ = true;
    return false;
}
bool Controls::Retire(StopReason reason, Owner next, Token token,
                      std::optional<std::uint64_t> next_scene) noexcept {
    const auto old = grant_;
    const bool stopped = StopActive(reason);
    if (grant_.generation == std::numeric_limits<std::uint64_t>::max()) {
        available_ = false;
        grant_.owner = Owner::none;
        return false;
    }
    ++grant_.generation;
    grant_.owner = next;
    grant_.token = token;
    if (next_scene) { grant_.scene = *next_scene; }
    actuator_.Revoked(old, grant_, reason);
    return stopped;
}
void Controls::Inhibit(StopReason reason) noexcept {
    if (grant_.owner != Owner::none) { (void)Retire(reason, Owner::none); }
    keyboard_armed_ = controller_armed_ = drag_armed_ = false;
    drag_pending_ = drag_active_ = previous_drag_down_ = false;
    foreground_ = false;
}
Result Controls::Configure(const Settings& settings) noexcept {
    if (!ValidSettings(settings)) { return Result::invalid; }
    Inhibit(StopReason::disabled);
    settings_ = settings;
    faulted_ = camera_faulted_ = false;
    available_ = false;
    has_tick_ = false;
    return pending_stop_ ? Result::stop_failed : Result::accepted;
}
bool Controls::ConsumesKey(std::uint16_t key) const noexcept {
    if (!settings_.enabled || !settings_.keyboard || !available_ || !foreground_) { return false; }
    return std::find(settings_.keys.begin(), settings_.keys.end(), key) != settings_.keys.end();
}
Result Controls::AcquireAutomation(std::uint64_t expected, Token token, Grant& output) noexcept {
    if (expected != grant_.generation) { return Result::stale; }
    if (!ValidTokenText(token.worker) || !ValidTokenText(token.operation)) { return Result::invalid; }
    if (!available_) { return Result::unavailable; }
    if (!foreground_ || (grant_.owner == Owner::manual && moving_)) { return Result::inhibited; }
    if (!RetryStop()) { return Result::stop_failed; }
    if (!Retire(StopReason::takeover, Owner::automation, token)) { return Result::stop_failed; }
    output = grant_;
    return Result::accepted;
}
Result Controls::AutomationDestination(const Grant& grant, GroundPoint point) noexcept {
    if (grant != grant_ || grant.owner != Owner::automation) { return Result::stale; }
    if (!Finite(point)) { return Result::invalid; }
    if (!available_ || !foreground_) { return Result::inhibited; }
    if (!RetryStop()) { return Result::stop_failed; }
    const bool start = !moving_;
    // A failing adapter can have partially submitted work. Retain stop responsibility.
    moving_ = true;
    if (!actuator_.Destination(grant_, point, start)) {
        Inhibit(StopReason::binding_failure);
        faulted_ = true;
        available_ = false;
        return Result::unavailable;
    }
    return Result::accepted;
}
Result Controls::Stop(const Grant& grant, StopReason reason) noexcept {
    if (grant != grant_) { return Result::stale; }
    return Retire(reason, Owner::none) ? Result::accepted : Result::stop_failed;
}
void Controls::Shutdown() noexcept {
    Inhibit(StopReason::shutdown);
    (void)RetryStop();
    available_ = false;
}

void Controls::Tick(const Input& input) noexcept {
    if (input.scene != grant_.scene) {
        const auto old = grant_;
        actuator_.SceneRetired(old.scene);
        // Never invoke an old actor's stop on a replacement actor or reused pointer.
        moving_ = pending_stop_ = false;
        (void)Retire(StopReason::scene_changed, Owner::none, {}, input.scene);
        Inhibit(StopReason::scene_changed);
        has_tick_ = false;
    }
    const bool discontinuity = has_tick_ &&
        (input.tick_ms < last_tick_ || input.tick_ms - last_tick_ > 250);
    const float seconds = !has_tick_ || discontinuity ? 0.0F
        : static_cast<float>(input.tick_ms - last_tick_) / 1000.0F;
    last_tick_ = input.tick_ms;
    has_tick_ = true;
    available_ = settings_.enabled && !faulted_ && input.native_available && input.scene != 0;
    if (!available_ || !input.exact_foreground || input.ui_owns_input || discontinuity) {
        Inhibit(!settings_.enabled ? StopReason::disabled : !input.native_available
            ? StopReason::binding_failure : discontinuity ? StopReason::stalled
            : !input.exact_foreground ? StopReason::focus : StopReason::ui);
        if (input.native_available) { (void)RetryStop(); }
        return;
    }
    foreground_ = true;
    if (!RetryStop()) { return; }

    const bool all_keys_up = std::all_of(settings_.keys.begin(), settings_.keys.end(),
        [&](auto key) { return !input.keys[key]; });
    if (all_keys_up) { keyboard_armed_ = true; }
    Vector2 direction{};
    if (settings_.keyboard && keyboard_armed_) {
        direction = RadialDirection({
            static_cast<float>(input.keys[settings_.keys[3]]) - input.keys[settings_.keys[2]],
            static_cast<float>(input.keys[settings_.keys[0]]) - input.keys[settings_.keys[1]]}, 0);
    }

    const bool connected = settings_.controller && input.controller_connected
        && input.controller_slot == settings_.controller_slot
        && Finite(input.left_stick) && Finite(input.right_stick);
    const bool lost_controller = controller_connected_ && !connected;
    if (!connected || !controller_connected_) { controller_armed_ = false; }
    controller_connected_ = connected;
    const auto stick = RadialDirection(input.left_stick, settings_.movement_dead_zone);
    const auto camera = RadialCamera(input.right_stick, settings_.camera_dead_zone);
    if (connected && !Nonzero(stick) && !Nonzero(camera)
        && Finite(input.left_stick) && Finite(input.right_stick)) { controller_armed_ = true; }
    if (connected && controller_armed_ && !camera_faulted_ && seconds > 0 && Nonzero(camera)) {
        const float scale = settings_.camera_radians_per_second * seconds;
        if (!actuator_.Camera({camera.x * scale * (settings_.invert_camera_x ? -1 : 1),
                              camera.y * scale * (settings_.invert_camera_y ? -1 : 1)})) {
            // Camera is not a movement owner. Latch its capability failure without
            // revoking an unrelated route or suppressing working movement controls.
            camera_faulted_ = true;
        }
    }
    if (!Nonzero(direction) && connected && controller_armed_) { direction = stick; }

    const bool drag_down = settings_.drag && input.keys[settings_.drag_button];
    if (!drag_down) { drag_armed_ = true; }
    if (drag_down && !previous_drag_down_ && drag_armed_) {
        drag_pending_ = input.pointer_in_world && input.ground_valid && Finite(input.ground)
            && std::isfinite(input.pointer_x) && std::isfinite(input.pointer_y);
        drag_origin_x_ = input.pointer_x;
        drag_origin_y_ = input.pointer_y;
    }
    previous_drag_down_ = drag_down;
    const bool lost_capture = (drag_pending_ || drag_active_)
        && (!input.pointer_in_world || !input.capture_valid);
    if (!drag_down || lost_capture) {
        drag_active_ = drag_pending_ = false;
        if (lost_capture) { drag_armed_ = false; }
    }
    if (drag_pending_ && drag_down && std::isfinite(input.pointer_x)
        && std::isfinite(input.pointer_y)
        && std::hypot(input.pointer_x - drag_origin_x_, input.pointer_y - drag_origin_y_)
            >= settings_.drag_threshold_pixels) {
        drag_pending_ = false;
        drag_active_ = true;
    }
    // Explicit precedence for simultaneous inputs: directional keys/stick, then drag.
    // No flat-plane fallback: losing a valid terrain pick stops an active drag.
    const bool destination = !Nonzero(direction) && drag_active_
        && input.ground_valid && Finite(input.ground);
    const bool directional = Nonzero(direction) && Basis(input);
    if (directional || destination) {
        if (grant_.owner != Owner::manual &&
            !Retire(StopReason::takeover, Owner::manual)) { return; }
        const bool start = !moving_;
        moving_ = true;
        const bool accepted = directional
            ? actuator_.Direction(grant_, WorldDirection(direction, input), start)
            : actuator_.Destination(grant_, input.ground, start);
        if (!accepted) {
            Inhibit(StopReason::binding_failure);
            faulted_ = true;
            available_ = false;
        }
    } else if (grant_.owner == Owner::manual && moving_) {
        (void)StopActive(lost_controller ? StopReason::device_lost
            : lost_capture ? StopReason::capture_lost : StopReason::release);
    }
}
} // namespace wonderbane::extension::movement
