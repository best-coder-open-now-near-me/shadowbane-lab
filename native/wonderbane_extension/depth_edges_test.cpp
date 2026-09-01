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

float WindowDepthForEyeDistance(
    const float eye_distance,
    const float projection_10,
    const float projection_11,
    const float projection_14
) noexcept {
    const float eye_z = -eye_distance;
    const float ndc = (
        projection_10 * eye_z + projection_14
    ) / (projection_11 * eye_z);
    return (ndc + 1.0F) * 0.5F;
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

    const std::array<float, 8U> continuous{
        WindowDepthForEyeDistance(
            1.0F / 0.099F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.101F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.098F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.102F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.097F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.096F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.104F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            1.0F / 0.103F, projection_10, projection_11, projection_14
        ),
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
    const float finite_background_center = WindowDepthForEyeDistance(
        20.0F, projection_10, projection_11, projection_14
    );
    std::array<float, 8U> finite_background{
        WindowDepthForEyeDistance(
            10.0F, projection_10, projection_11, projection_14
        ),
        WindowDepthForEyeDistance(
            20.2F, projection_10, projection_11, projection_14
        ),
        finite_background_center,
        finite_background_center,
        finite_background_center,
        finite_background_center,
        finite_background_center,
        finite_background_center,
    };
    if (IsForegroundDepthDiscontinuity(
            finite_background_center,
            finite_background.data(),
            finite_background.size(),
            projection_10,
            projection_11,
            projection_14
        )) {
        return Fail(L"finite background-side edge rejection");
    }

    const char* const fragment = DepthEdgeFragmentSource();
    if (fragment == nullptr
        || std::strstr(fragment, "wbTexelSize") == nullptr
        || std::strstr(fragment, "wbForegroundPairCurvature") == nullptr
        || std::strstr(fragment, "center <= (first + second) * 0.5") == nullptr
        || std::strstr(fragment, "upRight") != nullptr
        || std::strstr(fragment, "response <= wbEdgeThreshold") == nullptr
        || std::strstr(fragment, "wbAdaptiveOutlineEnabled") == nullptr
        || std::strstr(fragment, "wbSceneColorTexture") == nullptr
        || std::strstr(fragment, "wbSceneColorAvailable") == nullptr
        || std::strstr(fragment, "dot(sceneColor, vec3(0.2126, 0.7152, 0.0722))")
            == nullptr
        || std::strstr(fragment, "sceneColor / maximumChannel") == nullptr
        || std::strstr(fragment, "smoothstep(0.36, 0.70, luminance)") == nullptr
        || std::strstr(fragment, "discard") == nullptr) {
        return Fail(L"fixed-pixel depth shader contract");
    }
    return 0;
}
