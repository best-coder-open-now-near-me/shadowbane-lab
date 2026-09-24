#pragma once
#include "furnishing_selection.h"
namespace wonderbane::extension::furnishing {
// Coordinates are native UI pixels after NativeClientPoint conversion.
bool LayoutContains(const Selection&, int x, int y) noexcept;
// Compose a floor-local point and quarter-turn heading with occupied-building
// TQS. Nonuniform building scale is unavailable: rotated TQS would need shear.
bool CandidatePose(const Selection&, const std::array<float,3>& floor_point,
                   unsigned quarter_turns, Transform&) noexcept;
}
