#pragma once
#include "graphics_status.h"
#include <array>
#include <cstdint>

namespace wonderbane::extension::cue {
struct Identity {
    std::uint32_t actor = 0, type = 0, uuid = 0, zone = 0, render = 0;
    bool operator==(const Identity&) const = default;
    bool valid() const noexcept { return actor && type && uuid && zone && render; }
};
struct Settings {
    std::uint32_t enabled = 0;
    std::array<float, 3> color{0.2F, 0.85F, 1.0F};
    float opacity = 0.8F, radius = 5.0F, indicator_size = 24.0F;
    float indicator_y = 0.18F;
};
bool ValidSettings(const Settings&) noexcept;
struct Direction {
    bool available = false, offscreen = false;
    int turn = 0; // -1 left, +1 right, 0 aligned horizontally.
    float radians = 0;
};
class Tracker {
public:
    Direction Update(const Identity&, const float* position,
                     const GraphicsCameraState*, bool enabled) noexcept;
    void Reset() noexcept { identity_ = {}; offscreen_ = false; side_ = 0; }
private:
    Identity identity_{};
    bool offscreen_ = false;
    int side_ = 0;
};
} // namespace wonderbane::extension::cue
