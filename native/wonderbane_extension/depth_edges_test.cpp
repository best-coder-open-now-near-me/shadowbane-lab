#include "depth_edges.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace {

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

}  // namespace

int wmain() {
    using wonderbane::extension::DepthEdgeFragmentSource;
    using wonderbane::extension::IsForegroundDepthDiscontinuity;
    using wonderbane::extension::ReconstructPerspectiveEyeDepth;

    constexpr float projection_10 = -1.002002F;
    constexpr float projection_11 = -1.0F;
    constexpr float projection_14 = -0.2002002F;
    const float near_depth = ReconstructPerspectiveEyeDepth(
        0.99099099F, projection_10, projection_11, projection_14
    );
    if (!std::isfinite(near_depth) || std::fabs(near_depth - 10.0F) > 0.02F) {
        return Fail(L"perspective depth reconstruction");
    }

    constexpr std::array<float, 8U> continuous{
        0.9909910F, 0.9909920F, 0.9909900F, 0.9909915F,
        0.9909905F, 0.9909912F, 0.9909908F, 0.9909911F,
    };
    if (IsForegroundDepthDiscontinuity(
            0.99099099F,
            continuous.data(),
            continuous.size(),
            projection_10,
            projection_11,
            projection_14
        )) {
        return Fail(L"continuous surface rejection");
    }
    std::array<float, 8U> silhouette = continuous;
    silhouette[3] = 1.0F;
    if (!IsForegroundDepthDiscontinuity(
            0.99099099F,
            silhouette.data(),
            silhouette.size(),
            projection_10,
            projection_11,
            projection_14
        )) {
        return Fail(L"foreground silhouette acceptance");
    }
    if (IsForegroundDepthDiscontinuity(
            1.0F,
            silhouette.data(),
            silhouette.size(),
            projection_10,
            projection_11,
            projection_14
        )) {
        return Fail(L"background-side edge rejection");
    }

    const char* const fragment = DepthEdgeFragmentSource();
    if (fragment == nullptr
        || std::strstr(fragment, "wbTexelSize") == nullptr
        || std::strstr(fragment, "center * 0.0125") == nullptr
        || std::strstr(fragment, "discard") == nullptr) {
        return Fail(L"fixed-pixel depth shader contract");
    }
    return 0;
}
