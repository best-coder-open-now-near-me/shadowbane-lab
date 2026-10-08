#pragma once
#include <cmath>
#include <cstdint>
#include "camera.h"
namespace steam_wasd {
// All policy runs on the game window thread. Blocking requires a fresh neutral
// sample, so a key held through chat, alt-tab, or a scene change cannot restart.
enum Key : unsigned { w = 1, a = 2, s = 4, d = 8 };
inline Direction direction(unsigned keys, CameraBasis basis) {
    float forward = float(bool(keys & w)) - float(bool(keys & s));
    float right = float(bool(keys & d)) - float(bool(keys & a));
    const float length = std::hypot(forward, right);
    if (!length || !basis.valid) return {};
    forward /= length; right /= length;
    const Direction local{basis.forward.x*forward+basis.right.x*right,
                          basis.forward.z*forward+basis.right.z*right};
    const float local_length=std::hypot(local.x,local.z);
    if(!std::isfinite(local_length) || local_length<1e-6F) return {};
    return {local.x/local_length,local.z/local_length};
}
struct Controls {
    bool armed = false, moving = false;
    struct Result { bool stop{}, steer{}; Direction vector{}; };
    Result sample(unsigned keys, CameraBasis basis, bool permitted, bool same_scene) {
        Result result{};
        if (!same_scene || !permitted || !basis.valid) {
            result.stop = moving && same_scene;
            armed = moving = false;
            return result;
        }
        if (!keys) armed = true;
        const auto v = direction(keys, basis);
        const bool next = armed && (v.x != 0 || v.z != 0);
        result.stop = moving && !next;
        result.steer = next; result.vector = v;
        moving = next;
        return result;
    }
    void block() { armed = false; }
};
}
