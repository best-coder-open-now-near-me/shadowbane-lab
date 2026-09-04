#pragma once

#include <cstddef>

namespace wonderbane::extension {

struct CelBandColor {
    float red;
    float green;
    float blue;
};

std::size_t CelBandIndex(float intensity) noexcept;
CelBandColor CelBandForIntensity(float intensity) noexcept;
bool IsBandedLightingSceneState(bool depth_writes, bool blend_enabled) noexcept;
const char* BandedLightingFragmentSource() noexcept;
const char* BandedLightingVertexSource() noexcept;

struct BandedLightingDraw {
    int previous_program = 0;
    bool active = false;
};

bool BeginBandedLightingDraw(BandedLightingDraw* draw) noexcept;
void EndBandedLightingDraw(BandedLightingDraw* draw) noexcept;
void ResetBandedLighting() noexcept;

}  // namespace wonderbane::extension
