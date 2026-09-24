#pragma once
#include "furnishing_selection.h"
namespace wonderbane::extension::furnishing {
// Coordinates are client pixels, matching the native HUD rectangle getter.
bool LayoutContains(const Selection&, int x, int y) noexcept;
// Compose a floor-local point and quarter-turn heading with occupied-building
// TQS. Nonuniform building scale is unavailable: rotated TQS would need shear.
bool CandidatePose(const Selection&, const std::array<float,3>& floor_point,
                   unsigned quarter_turns, Transform&) noexcept;
}
