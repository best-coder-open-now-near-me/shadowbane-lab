#include "selected_cue.h"
#include <cmath>

namespace wonderbane::extension::cue {
bool ValidSettings(const Settings& s) noexcept {
    const auto in = [](float v, float lo, float hi) { return std::isfinite(v) && v >= lo && v <= hi; };
    return s.enabled <= 1U && in(s.opacity, 0.05F, 1.0F) && in(s.radius, 1.0F, 12.0F)
        && in(s.indicator_size, 12.0F, 64.0F) && in(s.indicator_y, 0.12F, 0.75F)
        && in(s.color[0], 0, 1) && in(s.color[1], 0, 1) && in(s.color[2], 0, 1);
}
Direction Tracker::Update(const Identity& id, const float* p,
                          const GraphicsCameraState* c, bool enabled) noexcept {
    if (!enabled || !id.valid() || !p || !c || c->viewport[2] <= 0 || c->viewport[3] <= 0) {
        Reset(); return {};
    }
    for (int i = 0; i < 3; ++i) {
        if (!std::isfinite(p[i]) || !std::isfinite(c->position[i]) || !std::isfinite(c->forward[i])) {
            Reset(); return {};
        }
    }
    for (int i = 0; i < 16; ++i) {
        if (!std::isfinite(c->view_matrix[i]) || !std::isfinite(c->projection_matrix[i])) {
            Reset(); return {};
        }
    }
    if (!(id == identity_)) { Reset(); identity_ = id; }
    float eye[4]{}, clip[4]{};
    for (int r = 0; r < 4; ++r) {
        eye[r] = c->view_matrix[r] * p[0] + c->view_matrix[4+r] * p[1]
            + c->view_matrix[8+r] * p[2] + c->view_matrix[12+r];
    }
    for (int r = 0; r < 4; ++r) {
        for (int k = 0; k < 4; ++k) clip[r] += c->projection_matrix[k*4+r] * eye[k];
        if (!std::isfinite(clip[r])) { Reset(); return {}; }
    }
    const float margin = offscreen_ ? 0.96F : 1.02F;
    const bool in = clip[3] > 0.00001F && std::abs(clip[0]) <= margin * clip[3]
        && std::abs(clip[1]) <= margin * clip[3]
        && clip[2] >= -clip[3] && clip[2] <= clip[3];
    offscreen_ = !in;
    const double dx = static_cast<double>(p[0]) - c->position[0];
    const double dz = static_cast<double>(p[2]) - c->position[2];
    const double fx = c->forward[0], fz = c->forward[2];
    if (fx*fx + fz*fz < 1e-10) { Reset(); return {}; }
    const float angle = static_cast<float>(std::atan2(-fz*dx + fx*dz, fx*dx + fz*dz));
    const int candidate = angle < 0 ? -1 : 1;
    // Three-degree tie band around directly behind. Only this ambiguous region
    // retains the previous side; leaving it restores the shortest turn.
    if (side_ == 0 || std::abs(angle) < 3.0892328F) side_ = candidate;
    const int turn = std::abs(angle) < 0.0523599F ? 0 : side_;
    return {true, offscreen_, turn, angle};
}
} // namespace wonderbane::extension::cue
