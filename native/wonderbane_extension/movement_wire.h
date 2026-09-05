#pragma once
#include "movement_controls.h"
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstring>

// Schema 2 fixed-width little-endian IPC payloads. Never serialize C++ policy
// object layout: Owner, bool and padding are not part of the wire contract.
namespace wonderbane::extension::movement::wire {
constexpr std::uint32_t schema = 2, command_size = 768, result_size = 512, status_size = 512;
constexpr std::uint32_t command_prefix = 192, result_prefix = 128;
enum class Verb : std::uint32_t { acquire = 3, destination = 4, stop = 5, configure = 6, pause = 7 };
#pragma pack(push, 1)
struct Host { std::uint32_t process = 0, generation = 0; std::uint64_t creation = 0; };
struct Token { char worker[96]{}, operation[96]{}; };
struct Grant { std::uint64_t generation = 0, scene = 0; std::uint32_t owner = 0, reserved = 0; Token token{}; };
struct Settings {
    std::uint32_t magic = 0x57424d43, version = 1, flags = 0;
    std::array<std::uint32_t, 4> keys{};
    std::uint32_t slot = 0;
    float movement_zone = 0, camera_zone = 0, sensitivity = 0, threshold = 0;
    std::uint32_t button = 0;
};
struct Command {
    Host host{}; std::uint64_t window = 0; Grant expected{};
    std::array<std::uint8_t, 16> request{}; GroundPoint destination{};
    Settings settings{}; std::uint64_t revision = 0; Token requested{};
    std::uint8_t reserved[56]{};
};
struct Receipt {
    Grant grant{}; std::array<std::uint8_t, 16> request{}; Host host{};
    std::uint64_t window = 0, revision = 0; Settings settings{};
    std::uint32_t outcome = 0, flags = 0; std::uint8_t reserved[60]{};
};
struct Status {
    std::int64_t sequence = 0; std::uint32_t process = 0, flags = 0;
    std::uint64_t creation = 0, window = 0; Grant grant{};
    Settings settings{}; std::uint64_t revision = 0, tick = 0;
    std::uint8_t reserved[196]{};
};
#pragma pack(pop)
static_assert(sizeof(Host) == 16 && sizeof(Token) == 192 && sizeof(Grant) == 216);
static_assert(sizeof(Settings) == 52 && sizeof(Command) == command_size - command_prefix);
static_assert(sizeof(Receipt) == result_size - result_prefix && sizeof(Status) == status_size);
static_assert(offsetof(Command, expected) == 24 && offsetof(Command, request) == 240);
static_assert(offsetof(Command, requested) == 328 && offsetof(Receipt, host) == 232);
static_assert(offsetof(Status, grant) == 32 && offsetof(Status, revision) == 300);
// Status flags describe observations only; none confers a command lease.
constexpr std::uint32_t bindings = 1, ready = 2, camera = 4, terminal = 8,
    controller_api = 16, controller_connected = 32, known_flags = 63;
inline bool Zero(const void* bytes, std::size_t count) noexcept {
    const auto* p = static_cast<const unsigned char*>(bytes);
    return std::all_of(p, p + count, [](unsigned char c) { return c == 0; });
}
inline bool Text(const char (&value)[96], bool required) noexcept {
    const auto* end = static_cast<const char*>(std::memchr(value, 0, 96));
    if (!end || (required && end == value)) { return false; }
    for (auto* p = value; p != end; ++p) { if (*p < 0x20 || *p > 0x7e) { return false; } }
    return Zero(end, 96 - static_cast<std::size_t>(end - value));
}
inline bool Decode(const Token& value, movement::Token& out, bool required) noexcept {
    if (!Text(value.worker, required) || !Text(value.operation, required)) { return false; }
    std::memcpy(out.worker.data(), value.worker, 96); std::memcpy(out.operation.data(), value.operation, 96); return true;
}
inline Token Encode(const movement::Token& value) noexcept {
    Token out{}; std::memcpy(out.worker, value.worker.data(), 96); std::memcpy(out.operation, value.operation.data(), 96); return out;
}
inline bool Decode(const Grant& value, movement::Grant& out) noexcept {
    if (!value.generation || value.owner > 2 || value.reserved) { return false; }
    movement::Grant next{};
    if (!Decode(value.token, next.token, value.owner == 1)) { return false; }
    if (value.owner != 1 && !Zero(&value.token, sizeof(value.token))) { return false; }
    if (value.owner != 0 && !value.scene) { return false; }
    next.generation = value.generation; next.scene = value.scene;
    next.owner = static_cast<Owner>(value.owner); out = next; return true;
}
inline Grant Encode(const movement::Grant& value) noexcept {
    return {value.generation, value.scene, static_cast<std::uint32_t>(value.owner), 0, Encode(value.token)};
}
inline Settings Encode(const movement::Settings& s) noexcept {
    Settings value{};
    value.flags = (s.enabled ? 1U : 0U) | (s.keyboard ? 2U : 0U) | (s.controller ? 4U : 0U)
        | (s.drag ? 8U : 0U) | (s.invert_camera_x ? 16U : 0U) | (s.invert_camera_y ? 32U : 0U);
    for (std::size_t i = 0; i < 4; ++i) { value.keys[i] = s.keys[i]; }
    value.slot = s.controller_slot; value.movement_zone = s.movement_dead_zone;
    value.camera_zone = s.camera_dead_zone; value.sensitivity = s.camera_radians_per_second;
    value.threshold = s.drag_threshold_pixels; value.button = s.drag_button; return value;
}
inline bool Decode(const Settings& value, movement::Settings& s) noexcept {
    if (value.magic != 0x57424d43 || value.version != 1 || (value.flags & ~63U) || value.button > 255) { return false; }
    movement::Settings next{};
    next.enabled = (value.flags & 1) != 0; next.keyboard = (value.flags & 2) != 0;
    next.controller = (value.flags & 4) != 0; next.drag = (value.flags & 8) != 0;
    next.invert_camera_x = (value.flags & 16) != 0; next.invert_camera_y = (value.flags & 32) != 0;
    for (std::size_t i = 0; i < 4; ++i) {
        if (value.keys[i] > 255) { return false; } next.keys[i] = static_cast<std::uint16_t>(value.keys[i]);
    }
    next.controller_slot = value.slot; next.movement_dead_zone = value.movement_zone;
    next.camera_dead_zone = value.camera_zone; next.camera_radians_per_second = value.sensitivity;
    next.drag_threshold_pixels = value.threshold; next.drag_button = static_cast<std::uint16_t>(value.button);
    if (!ValidSettings(next)) { return false; } s = next; return true;
}
inline bool Valid(const Host& host) noexcept {
    return host.process && host.process <= 0x7fffffffU && host.generation && host.generation <= 0x7fffffffU && host.creation;
}
inline bool Valid(Verb verb, const Command& value) noexcept {
    movement::Grant grant{}; movement::Token token{}; movement::Settings settings{};
    if (!Valid(value.host) || !value.window || value.window > UINT32_MAX
        || !Decode(value.expected, grant) || Zero(value.request.data(), value.request.size())
        || !Decode(value.settings, settings) || !Zero(value.reserved, sizeof(value.reserved))) { return false; }
    if (verb == Verb::acquire) {
        return !Zero(value.request.data(), value.request.size()) && Decode(value.requested, token, true);
    }
    if (!Zero(&value.requested, sizeof(value.requested))) { return false; }
    if (verb == Verb::destination) {
        return grant.owner == Owner::automation && std::isfinite(value.destination.x)
            && std::isfinite(value.destination.y) && std::isfinite(value.destination.z);
    }
    if (verb == Verb::stop || verb == Verb::pause) { return grant.owner == Owner::automation; }
    if (verb == Verb::configure) { return value.revision && Decode(value.settings, settings); }
    return false;
}
} // namespace wonderbane::extension::movement::wire
