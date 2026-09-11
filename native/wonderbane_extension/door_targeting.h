#pragma once
#include "movement_controls.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>

namespace wonderbane::extension::movement {
// Structure identity followed by the door sub-object key. Doors can share the
// structure identity at ArcObj+0x18, so that field alone is not a unique door key.
using DoorIdentity = std::array<std::uint32_t, 4>;
struct DoorGeometry {
    DoorIdentity identity{};
    GroundPoint center{}; // Verified native world coordinates, never parent-local.
    bool eligible = false;
    bool unobstructed = false;
};
struct DoorChoice { DoorGeometry door{}; float distance = 0, alignment = 0, score = 0; };
// Stream a bounded native enumeration through this policy. No camera, pointer,
// actor writes, cached object pointers, or native authority belong in ranking.
class DoorRanking {
public:
    DoorRanking(GroundPoint origin, Vector2 forward, DoorIdentity previous = {}) noexcept
        : origin_(origin), previous_(previous) {
        const auto length = std::hypot(forward.x, forward.y);
        valid_ = Finite(origin) && std::isfinite(length) && length > 0.0001F;
        if (valid_) { forward_ = {forward.x / length, forward.y / length}; }
    }
    void Consider(const DoorGeometry& door) noexcept {
        if (!valid_ || !door.eligible || !door.unobstructed || door.identity == DoorIdentity{}
            || !Finite(door.center)) { return; }
        const float dx = door.center.x - origin_.x, dz = door.center.z - origin_.z;
        const float vertical = std::abs(door.center.y - origin_.y);
        const auto distance = std::hypot(dx, dz);
        if (!std::isfinite(distance) || distance <= 0.0001F || distance > range || vertical > vertical_range) { return; }
        const float alignment = (dx * forward_.x + dz * forward_.y) / distance;
        if (!std::isfinite(alignment) || alignment < minimum_alignment) { return; }
        DoorChoice choice{door, distance, alignment, distance / range + .8F * (1 - alignment)};
        if (door.identity == previous_) { previous_choice_ = choice; }
        if (!best_ || choice.score < best_->score
            || (choice.score == best_->score && choice.door.identity < best_->door.identity)) { best_ = choice; }
    }
    std::optional<DoorChoice> Choice() const noexcept {
        // Small hysteresis prevents flickering between nearly equivalent doors.
        // A blocked, out-of-cone, or absent previous door never remains eligible.
        if (best_ && previous_choice_ && previous_choice_->score <= best_->score + .08F) { return previous_choice_; }
        return best_;
    }
    static constexpr float range = 6.0F;
    static constexpr float vertical_range = 2.5F;
    static constexpr float minimum_alignment = .70710678118F; // 90-degree full cone.
private:
    static bool Finite(GroundPoint p) noexcept {
        return std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z);
    }
    GroundPoint origin_{};
    Vector2 forward_{};
    DoorIdentity previous_{};
    std::optional<DoorChoice> best_, previous_choice_;
    bool valid_ = false;
};
}
