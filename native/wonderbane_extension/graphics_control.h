#pragma once

#include <Windows.h>

#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

constexpr std::uint32_t kGraphicsControlMagic = 0x43474257U;  // "WBGC"
constexpr std::uint32_t kGraphicsControlSchemaVersion = 2U;
constexpr std::uint32_t kGraphicsControlBandedLighting = 1U << 0U;
constexpr std::uint32_t kGraphicsControlDepthContours = 1U << 1U;
constexpr std::uint32_t kGraphicsControlFeatureAccents = 1U << 2U;
constexpr std::uint32_t kGraphicsControlAdaptiveOutlines = 1U << 3U;
constexpr std::uint32_t kGraphicsControlKnownFlags =
    kGraphicsControlBandedLighting
    | kGraphicsControlDepthContours
    | kGraphicsControlFeatureAccents
    | kGraphicsControlAdaptiveOutlines;

enum class DepthContourMode : std::uint32_t {
    legacy = 0U,
    sustained = 1U,
};

enum class DepthContourDebugMode : std::uint32_t {
    none = 0U,
    response = 1U,
    sustained_response = 2U,
    support = 3U,
    rejected = 4U,
};

struct GraphicsParameters {
    std::uint32_t flags = 0U;
    std::array<float, 3U> dark_scene_outline{};
    float dark_scene_outline_strength = 0.0F;
    float bright_scene_ink_alpha = 0.0F;
    float depth_edge_threshold = 0.0F;
    std::array<float, 3U> band_thresholds{};
    std::array<std::array<float, 3U>, 4U> band_colors{};
    float vertex_tint_gamma = 0.0F;
    float distant_highlight_compression = 0.0F;
    float feature_outline_width = 0.0F;
    float sustained_edge_threshold = 0.0F;
    DepthContourMode depth_contour_mode = DepthContourMode::legacy;
    DepthContourDebugMode depth_contour_debug_mode = DepthContourDebugMode::none;
};

#pragma pack(push, 4)
struct GraphicsControlBlockV2 {
    std::uint32_t magic = 0U;
    std::uint32_t schema_version = 0U;
    std::uint32_t structure_size = 0U;
    std::uint32_t process_id = 0U;
    std::uint32_t process_creation_filetime_low = 0U;
    std::uint32_t process_creation_filetime_high = 0U;
    volatile LONG desired_sequence = 0;
    volatile LONG applied_sequence = 0;
    volatile LONG rejected_sequence = 0;
    volatile LONG last_error = ERROR_SUCCESS;
    std::uint32_t flags = 0U;
    float dark_scene_outline_red = 0.0F;
    float dark_scene_outline_green = 0.0F;
    float dark_scene_outline_blue = 0.0F;
    float dark_scene_outline_strength = 0.0F;
    float bright_scene_ink_alpha = 0.0F;
    float depth_edge_threshold = 0.0F;
    float band_threshold_0 = 0.0F;
    float band_threshold_1 = 0.0F;
    float band_threshold_2 = 0.0F;
    float band_color_0_red = 0.0F;
    float band_color_0_green = 0.0F;
    float band_color_0_blue = 0.0F;
    float band_color_1_red = 0.0F;
    float band_color_1_green = 0.0F;
    float band_color_1_blue = 0.0F;
    float band_color_2_red = 0.0F;
    float band_color_2_green = 0.0F;
    float band_color_2_blue = 0.0F;
    float band_color_3_red = 0.0F;
    float band_color_3_green = 0.0F;
    float band_color_3_blue = 0.0F;
    float vertex_tint_gamma = 0.0F;
    float distant_highlight_compression = 0.0F;
    float feature_outline_width = 0.0F;
    float sustained_edge_threshold = 0.0F;
    std::uint32_t depth_contour_mode = 0U;
    std::uint32_t depth_contour_debug_mode = 0U;
    std::uint32_t reserved[26U]{};
};
#pragma pack(pop)

static_assert(sizeof(GraphicsControlBlockV2) == 256U);
static_assert(offsetof(GraphicsControlBlockV2, desired_sequence) == 24U);
static_assert(offsetof(GraphicsControlBlockV2, flags) == 40U);
static_assert(offsetof(GraphicsControlBlockV2, feature_outline_width) == 136U);
static_assert(offsetof(GraphicsControlBlockV2, sustained_edge_threshold) == 140U);
static_assert(offsetof(GraphicsControlBlockV2, depth_contour_mode) == 144U);
static_assert(offsetof(GraphicsControlBlockV2, depth_contour_debug_mode) == 148U);

struct GraphicsParametersSnapshot {
    GraphicsParameters parameters{};
    std::uint32_t revision = 0U;
};

struct GraphicsControlStatus {
    bool available = false;
    wchar_t mapping_name[128U]{};
    LONG desired_sequence = 0;
    LONG applied_sequence = 0;
    LONG rejected_sequence = 0;
    DWORD last_error = ERROR_SUCCESS;
};

const char* DepthContourModeName(DepthContourMode mode) noexcept;
const char* DepthContourDebugModeName(DepthContourDebugMode mode) noexcept;
GraphicsParameters DefaultGraphicsParameters() noexcept;
bool ValidateGraphicsParameters(const GraphicsParameters& parameters) noexcept;
GraphicsParameters GraphicsParametersFromControlBlock(
    const GraphicsControlBlockV2& block
) noexcept;
void PopulateGraphicsControlBlock(
    GraphicsControlBlockV2* block,
    const GraphicsParameters& parameters,
    DWORD process_id,
    std::uint64_t process_creation_filetime_utc
) noexcept;

DWORD StartGraphicsControl() noexcept;
void ApplyPendingGraphicsControl() noexcept;
GraphicsParametersSnapshot SnapshotGraphicsParameters() noexcept;
GraphicsParameters CurrentGraphicsParameters() noexcept;
std::uint32_t CurrentGraphicsParametersRevision() noexcept;
void StopGraphicsControl() noexcept;
DWORD GetGraphicsControlName(
    wchar_t* destination,
    std::size_t destination_capacity
) noexcept;
GraphicsControlStatus GetGraphicsControlStatus() noexcept;

}  // namespace wonderbane::extension
