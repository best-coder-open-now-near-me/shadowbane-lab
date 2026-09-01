#include "banded_lighting.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>

namespace {

bool NearlyEqual(const float left, const float right) noexcept {
    return std::fabs(left - right) < 0.0001F;
}

bool HasColor(
    const wonderbane::extension::CelBandColor color,
    const float red,
    const float green,
    const float blue
) noexcept {
    return NearlyEqual(color.red, red)
        && NearlyEqual(color.green, green)
        && NearlyEqual(color.blue, blue);
}

int Fail(const char* const operation) noexcept {
    std::fprintf(stderr, "%s failed\n", operation);
    return 1;
}

}  // namespace

int main() {
    using wonderbane::extension::BandedLightingFragmentSource;
    using wonderbane::extension::CelBandForIntensity;
    using wonderbane::extension::CelBandIndex;

    if (CelBandIndex(-1.0F) != 0U || CelBandIndex(0.2199F) != 0U
        || CelBandIndex(0.22F) != 1U || CelBandIndex(0.4299F) != 1U
        || CelBandIndex(0.43F) != 2U || CelBandIndex(0.6599F) != 2U
        || CelBandIndex(0.66F) != 3U || CelBandIndex(1.0F) != 3U
        || CelBandIndex(std::numeric_limits<float>::infinity()) != 3U
        || CelBandIndex(std::numeric_limits<float>::quiet_NaN()) != 0U) {
        return Fail("band threshold contract");
    }
    if (!HasColor(CelBandForIntensity(0.1F), 0.20F, 0.20F, 0.20F)
        || !HasColor(CelBandForIntensity(0.3F), 0.48F, 0.53F, 0.61F)
        || !HasColor(CelBandForIntensity(0.5F), 0.72F, 0.76F, 0.80F)
        || !HasColor(CelBandForIntensity(0.8F), 1.00F, 0.98F, 0.92F)) {
        return Fail("band color contract");
    }

    const char* const source = BandedLightingFragmentSource();
    if (source == nullptr
        || std::strstr(source, "#version 120") == nullptr
        || std::strstr(source, "gl_Color.rgb") == nullptr
        || std::strstr(source, "gl_TexCoord[0].st") == nullptr
        || std::strstr(source, "gl_FogFragCoord") == nullptr
        || std::strstr(source, "wbFogMode == 2048") == nullptr
        || std::strstr(source, "wbFogMode == 2049") == nullptr) {
        return Fail("fragment-only compatibility contract");
    }
    return 0;
}
