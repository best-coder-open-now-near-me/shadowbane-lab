#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::movement {
// Stable semantic identifiers. Unknown/unverified actions are rejected, not exposed.
enum class ControllerAction : std::uint8_t { none = 0, movement = 1, camera = 2, cancel_movement = 3 };
enum class ControllerControl : std::uint8_t {
    none = 0, left_stick = 1, right_stick = 2, a = 3, b = 4, x = 5, y = 6,
    dpad_up = 7, dpad_down = 8, dpad_left = 9, dpad_right = 10,
    start = 11, back = 12, left_thumb = 13, right_thumb = 14,
    left_shoulder = 15, right_shoulder = 16, left_trigger = 17, right_trigger = 18
};
struct ControllerBinding {
    ControllerAction action = ControllerAction::none;
    ControllerControl control = ControllerControl::none;
    // Exact shoulder combination: 1 left, 2 right, 3 both. Base (0) is fallback.
    std::uint8_t modifiers = 0;
    bool operator==(const ControllerBinding&) const = default;
};
constexpr std::size_t controller_binding_capacity = 24;
struct ControllerProfile {
    std::array<ControllerBinding, controller_binding_capacity> bindings{{
        {ControllerAction::movement, ControllerControl::left_stick, 0},
        {ControllerAction::camera, ControllerControl::right_stick, 0},
        {ControllerAction::cancel_movement, ControllerControl::b, 0}}};
    bool operator==(const ControllerProfile&) const = default;
};
constexpr ControllerAction ResolveControllerAction(const ControllerProfile& profile,
    ControllerControl control, std::uint8_t modifiers) noexcept {
    ControllerAction fallback = ControllerAction::none;
    for (const auto& b : profile.bindings) {
        if (b.control != control || b.action == ControllerAction::none) { continue; }
        if (b.modifiers == modifiers) { return b.action; }
        if (!b.modifiers) { fallback = b.action; }
    }
    return fallback;
}
constexpr bool ValidControllerProfile(const ControllerProfile& profile) noexcept {
    bool ended = false; std::uint8_t modifiers_used = 0;
    for (std::size_t i = 0; i != profile.bindings.size(); ++i) {
        const auto& b = profile.bindings[i];
        if (b.action == ControllerAction::none) {
            if (b.control != ControllerControl::none || b.modifiers) { return false; }
            ended = true; continue;
        }
        if (ended || b.modifiers > 3 || b.action > ControllerAction::cancel_movement
            || b.control <= ControllerControl::none || b.control > ControllerControl::right_trigger) { return false; }
        const bool vector = b.control == ControllerControl::left_stick || b.control == ControllerControl::right_stick;
        if (vector != (b.action == ControllerAction::movement || b.action == ControllerAction::camera)) { return false; }
        modifiers_used |= b.modifiers;
        for (std::size_t j = 0; j != i; ++j) {
            if (profile.bindings[j].control == b.control && profile.bindings[j].modifiers == b.modifiers) { return false; }
        }
    }
    // A shoulder used as a modifier cannot itself trigger an action.
    for (const auto& b : profile.bindings) {
        if (((modifiers_used & 1) && b.control == ControllerControl::left_shoulder)
            || ((modifiers_used & 2) && b.control == ControllerControl::right_shoulder)) { return false; }
    }
    for (std::uint8_t modifiers = 0; modifiers != 4; ++modifiers) {
        const auto left = ResolveControllerAction(profile, ControllerControl::left_stick, modifiers);
        const auto right = ResolveControllerAction(profile, ControllerControl::right_stick, modifiers);
        if (left != ControllerAction::none && left == right) { return false; }
    }
    return true;
}
// Explicit fixed-width format, independent of enum/object layout. Bits 13..15 reserved.
constexpr std::uint16_t EncodeControllerBinding(ControllerBinding b) noexcept {
    return static_cast<std::uint16_t>(static_cast<unsigned>(b.action)
        | (static_cast<unsigned>(b.control) << 6) | (static_cast<unsigned>(b.modifiers) << 11));
}
constexpr bool DecodeControllerBinding(std::uint16_t value, ControllerBinding& out) noexcept {
    if (value & 0xe000U) { return false; }
    out = {static_cast<ControllerAction>(value & 63), static_cast<ControllerControl>((value >> 6) & 31),
        static_cast<std::uint8_t>((value >> 11) & 3)};
    return true; // Whole-profile validation rejects unsupported IDs and conflicts.
}
}
