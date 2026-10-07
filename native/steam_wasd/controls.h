#pragma once
#include <cmath>
#include <cstdint>
namespace steam_wasd {
// All policy runs on the game window thread. Blocking requires a fresh neutral
// sample, so a key held through chat, alt-tab, or a scene change cannot restart.
enum Key : unsigned { w = 1, a = 2, s = 4, d = 8 };
struct Direction { float x{}, z{}; };
inline Direction direction(unsigned keys, float yaw) {
    float forward = float(bool(keys & w)) - float(bool(keys & s));
    float right = float(bool(keys & d)) - float(bool(keys & a));
    const float length = std::hypot(forward, right);
    if (!length || !std::isfinite(yaw)) return {};
    forward /= length; right /= length;
    return {std::sin(yaw)*forward + std::cos(yaw)*right,
            -std::cos(yaw)*forward + std::sin(yaw)*right};
}
struct Controls {
    bool armed = false, moving = false;
    struct Result { bool stop{}, steer{}; Direction vector{}; };
    Result sample(unsigned keys, float yaw, bool permitted, bool same_scene) {
        Result result{};
        if (!same_scene || !permitted) {
            result.stop = moving && same_scene;
            armed = moving = false;
            return result;
        }
        if (!keys) armed = true;
        const auto v = direction(keys, yaw);
        const bool next = armed && (v.x != 0 || v.z != 0);
        result.stop = moving && !next;
        result.steer = next; result.vector = v;
        moving = next;
        return result;
    }
    void block() { armed = false; }
};
}
