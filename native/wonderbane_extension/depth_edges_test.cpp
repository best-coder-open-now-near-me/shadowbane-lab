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
    using wonderbane::extension::EvaluateDepthContour;
    using wonderbane::extension::IsForegroundDepthDiscontinuity;
    using wonderbane::extension::ReconstructPerspectiveEyeDepth;

    constexpr float projection_10 = -1.002002F;
    constexpr float projection_11 = -1.0F;
    constexpr float projection_14 = -0.2002002F;
    constexpr float edge_threshold = 0.055F;
    constexpr float support_threshold = 0.055F;
    const float center_depth = WindowDepthForEyeDistance(
        10.0F, projection_10, projection_11, projection_14
    );
    const float near_depth = ReconstructPerspectiveEyeDepth(
        center_depth, projection_10, projection_11, projection_14
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
    const auto continuous_result = EvaluateDepthContour(
        center_depth,
        continuous.data(),
        continuous.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (continuous_result.raw_candidate || continuous_result.accepted) {
        return Fail(L"continuous surface rejection");
    }

    std::array<float, 8U> one_pixel_crack{};
    one_pixel_crack.fill(center_depth);
    one_pixel_crack[0] = 1.0F;
    const auto legacy_crack = EvaluateDepthContour(
        center_depth,
        one_pixel_crack.data(),
        one_pixel_crack.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        false
    );
    const auto sustained_crack = EvaluateDepthContour(
        center_depth,
        one_pixel_crack.data(),
        one_pixel_crack.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!legacy_crack.accepted || !sustained_crack.raw_candidate
        || sustained_crack.accepted
        || sustained_crack.horizontal_support > 0.0001F) {
        return Fail(L"one-pixel recessed crack rejection");
    }

    std::array<float, 8U> finite_one_pixel_crack{};
    finite_one_pixel_crack.fill(center_depth);
    finite_one_pixel_crack[0] = WindowDepthForEyeDistance(
        20.0F, projection_10, projection_11, projection_14
    );
    const auto finite_crack_result = EvaluateDepthContour(
        center_depth,
        finite_one_pixel_crack.data(),
        finite_one_pixel_crack.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!finite_crack_result.raw_candidate || finite_crack_result.accepted
        || finite_crack_result.horizontal_support > 0.0001F) {
        return Fail(L"finite one-pixel recessed crack rejection");
    }

    std::array<float, 8U> opposite_side_support = one_pixel_crack;
    const float moderate_background = WindowDepthForEyeDistance(
        50.0F / 3.0F, projection_10, projection_11, projection_14
    );
    opposite_side_support[1] = moderate_background;
    opposite_side_support[5] = moderate_background;
    const auto opposite_side_result = EvaluateDepthContour(
        center_depth,
        opposite_side_support.data(),
        opposite_side_support.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!opposite_side_result.raw_candidate || opposite_side_result.accepted
        || opposite_side_result.horizontal_support > 0.0001F) {
        return Fail(L"dominant-direction support rejection");
    }

    std::array<float, 8U> infinite_silhouette{};
    infinite_silhouette.fill(center_depth);
    infinite_silhouette[0] = 1.0F;
    infinite_silhouette[4] = 1.0F;
    const auto infinite_result = EvaluateDepthContour(
        center_depth,
        infinite_silhouette.data(),
        infinite_silhouette.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!infinite_result.accepted || infinite_result.horizontal_support < 0.99F) {
        return Fail(L"persistent infinite background acceptance");
    }

    std::array<float, 8U> thin_foreground{};
    thin_foreground.fill(1.0F);
    const auto thin_foreground_result = EvaluateDepthContour(
        center_depth,
        thin_foreground.data(),
        thin_foreground.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!thin_foreground_result.accepted
        || thin_foreground_result.horizontal_support < 0.99F
        || thin_foreground_result.vertical_support < 0.99F) {
        return Fail(L"thin foreground acceptance");
    }

    std::array<float, 8U> finite_silhouette{};
    finite_silhouette.fill(center_depth);
    const float finite_background = WindowDepthForEyeDistance(
        20.0F, projection_10, projection_11, projection_14
    );
    finite_silhouette[0] = finite_background;
    finite_silhouette[4] = finite_background;
    const auto finite_result = EvaluateDepthContour(
        center_depth,
        finite_silhouette.data(),
        finite_silhouette.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!finite_result.accepted
        || finite_result.horizontal_support < 0.49F
        || finite_result.horizontal_support > 0.51F) {
        return Fail(L"persistent finite background acceptance");
    }

    std::array<float, 8U> unrelated_axis_support = one_pixel_crack;
    unrelated_axis_support[2] = finite_background;
    unrelated_axis_support[6] = finite_background;
    unrelated_axis_support[3] = WindowDepthForEyeDistance(
        20.0F / 3.0F, projection_10, projection_11, projection_14
    );
    unrelated_axis_support[7] = center_depth;
    const auto unrelated_result = EvaluateDepthContour(
        center_depth,
        unrelated_axis_support.data(),
        unrelated_axis_support.size(),
        projection_10,
        projection_11,
        projection_14,
        edge_threshold,
        support_threshold,
        true
    );
    if (!unrelated_result.raw_candidate || unrelated_result.accepted
        || unrelated_result.horizontal_support > 0.0001F
        || unrelated_result.vertical_support < 0.49F
        || unrelated_result.vertical_response > 0.001F) {
        return Fail(L"cross-axis support rejection");
    }

    std::array<float, 8U> shallow_slope{};
    shallow_slope[0] = WindowDepthForEyeDistance(
        10.1F, projection_10, projection_11, projection_14
    );
    shallow_slope[1] = WindowDepthForEyeDistance(
        9.9F, projection_10, projection_11, projection_14
    );
    shallow_slope[2] = center_depth;
    shallow_slope[3] = center_depth;
    shallow_slope[4] = WindowDepthForEyeDistance(
        10.2F, projection_10, projection_11, projection_14
    );
    shallow_slope[5] = WindowDepthForEyeDistance(
        9.8F, projection_10, projection_11, projection_14
    );
    shallow_slope[6] = center_depth;
    shallow_slope[7] = center_depth;
    if (EvaluateDepthContour(
            center_depth,
            shallow_slope.data(),
            shallow_slope.size(),
            projection_10,
            projection_11,
            projection_14,
            edge_threshold,
            support_threshold,
            true
        ).accepted) {
        return Fail(L"shallow terrain slope rejection");
    }

    std::array<float, 8U> sustained_slope{};
    sustained_slope[0] = WindowDepthForEyeDistance(
        12.0F, projection_10, projection_11, projection_14
    );
    sustained_slope[1] = WindowDepthForEyeDistance(
        9.0F, projection_10, projection_11, projection_14
    );
    sustained_slope[2] = center_depth;
    sustained_slope[3] = center_depth;
    sustained_slope[4] = WindowDepthForEyeDistance(
        14.0F, projection_10, projection_11, projection_14
    );
    sustained_slope[5] = WindowDepthForEyeDistance(
        8.0F, projection_10, projection_11, projection_14
    );
    sustained_slope[6] = center_depth;
    sustained_slope[7] = center_depth;
    if (!EvaluateDepthContour(
            center_depth,
            sustained_slope.data(),
            sustained_slope.size(),
            projection_10,
            projection_11,
            projection_14,
            edge_threshold,
            support_threshold,
            true
        ).accepted) {
        return Fail(L"sustained abrupt slope characterization");
    }

    if (EvaluateDepthContour(
            center_depth,
            one_pixel_crack.data(),
            4U,
            projection_10,
            projection_11,
            projection_14,
            edge_threshold,
            support_threshold,
            true
        ).accepted) {
        return Fail(L"missing second-ring rejection");
    }
    if (!IsForegroundDepthDiscontinuity(
            center_depth,
            one_pixel_crack.data(),
            one_pixel_crack.size(),
            projection_10,
            projection_11,
            projection_14
        )) {
        return Fail(L"legacy compatibility wrapper");
    }
    if (IsForegroundDepthDiscontinuity(
            1.0F,
            infinite_silhouette.data(),
            infinite_silhouette.size(),
            projection_10,
            projection_11,
            projection_14
        )) {
        return Fail(L"background-side edge rejection");
    }
    const float finite_background_center = WindowDepthForEyeDistance(
        20.0F, projection_10, projection_11, projection_14
    );
    std::array<float, 8U> finite_background_side{};
    finite_background_side.fill(finite_background_center);
    finite_background_side[0] = center_depth;
    finite_background_side[1] = WindowDepthForEyeDistance(
        20.2F, projection_10, projection_11, projection_14
    );
    if (EvaluateDepthContour(
            finite_background_center,
            finite_background_side.data(),
            finite_background_side.size(),
            projection_10,
            projection_11,
            projection_14,
            edge_threshold,
            support_threshold,
            true
        ).raw_candidate) {
        return Fail(L"finite background-side edge rejection");
    }

    const char* const fragment = DepthEdgeFragmentSource();
    if (fragment == nullptr
        || std::strstr(fragment, "wbTexelSize") == nullptr
        || std::strstr(fragment, "wbForegroundPairCurvature") == nullptr
        || std::strstr(fragment, "wbRelativeDrop") == nullptr
        || std::strstr(fragment, "wbSustainedEdgeThreshold") == nullptr
        || std::strstr(fragment, "wbDepthContourMode") == nullptr
        || std::strstr(fragment, "wbDepthContourDebugMode") == nullptr
        || std::strstr(fragment, "horizontalSupport") == nullptr
        || std::strstr(fragment, "verticalSupport") == nullptr
        || std::strstr(fragment, "sustainedResponse") == nullptr
        || std::strstr(fragment, "needsSecondRing") == nullptr
        || std::strstr(fragment, "wbTexelSize.x * 2.0") == nullptr
        || std::strstr(fragment, "wbTexelSize.y * 2.0") == nullptr
        || std::strstr(fragment, "wbDepthContourMode == 0") == nullptr
        || std::strstr(fragment, "bool accepted = rawCandidate || sustainedCandidate") != nullptr
        || std::strstr(fragment, "GL_LINEAR") != nullptr
        || std::strstr(fragment, "wbAdaptiveOutlineEnabled") == nullptr
        || std::strstr(fragment, "wbSceneColorTexture") == nullptr
        || std::strstr(fragment, "discard") == nullptr) {
        return Fail(L"sustained depth shader contract");
    }
    return 0;
}
