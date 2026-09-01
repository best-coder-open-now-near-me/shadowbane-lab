#include "graphics_control.h"

#include <strsafe.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {
namespace {

constexpr wchar_t kControlNameFormat[] =
    L"Local\\WonderBaneGraphicsControl-%lu-%llu";
constexpr std::size_t kControlNameCapacity = 128U;

HANDLE g_mapping = nullptr;
GraphicsControlBlockV1* g_control = nullptr;
wchar_t g_control_name[kControlNameCapacity]{};
std::array<GraphicsParameters, 2U> g_parameter_snapshots{{
    DefaultGraphicsParameters(),
    DefaultGraphicsParameters(),
}};
volatile LONG g_active_parameter_snapshot = 0;
volatile LONG g_parameter_revision = 1;

std::uint64_t FileTimeValue(const FILETIME value) noexcept {
    ULARGE_INTEGER combined{};
    combined.LowPart = value.dwLowDateTime;
    combined.HighPart = value.dwHighDateTime;
    return combined.QuadPart;
}

bool IsFiniteRange(const float value, const float minimum, const float maximum) noexcept {
    return std::isfinite(value) && value >= minimum && value <= maximum;
}

bool IsColor(const std::array<float, 3U>& color) noexcept {
    return std::all_of(color.begin(), color.end(), [](const float channel) {
        return IsFiniteRange(channel, 0.0F, 1.5F);
    });
}

void PublishParameters(const GraphicsParameters& parameters) noexcept {
    const LONG active = InterlockedCompareExchange(&g_active_parameter_snapshot, 0, 0);
    const LONG inactive = active == 0 ? 1 : 0;
    g_parameter_snapshots[static_cast<std::size_t>(inactive)] = parameters;
    MemoryBarrier();
    InterlockedExchange(&g_active_parameter_snapshot, inactive);
    InterlockedIncrement(&g_parameter_revision);
}

}  // namespace

GraphicsParameters DefaultGraphicsParameters() noexcept {
    GraphicsParameters parameters{};
    parameters.flags = kGraphicsControlBandedLighting
        | kGraphicsControlDepthContours
        | kGraphicsControlFeatureAccents
        | kGraphicsControlAdaptiveOutlines;
    parameters.dark_scene_outline = {0.52F, 0.56F, 0.70F};
    parameters.dark_scene_outline_strength = 0.28F;
    parameters.bright_scene_ink_alpha = 0.86F;
    parameters.depth_edge_threshold = 0.055F;
    parameters.band_thresholds = {0.22F, 0.43F, 0.66F};
    parameters.band_colors = {{
        {0.23F, 0.24F, 0.26F},
        {0.54F, 0.58F, 0.65F},
        {0.78F, 0.81F, 0.84F},
        {1.00F, 0.99F, 0.95F},
    }};
    parameters.vertex_tint_gamma = 0.78F;
    parameters.distant_highlight_compression = 0.45F;
    parameters.feature_outline_width = 1.35F;
    return parameters;
}

bool ValidateGraphicsParameters(const GraphicsParameters& parameters) noexcept {
    if ((parameters.flags & ~kGraphicsControlKnownFlags) != 0U
        || !IsColor(parameters.dark_scene_outline)
        || !IsFiniteRange(parameters.dark_scene_outline_strength, 0.0F, 1.0F)
        || !IsFiniteRange(parameters.bright_scene_ink_alpha, 0.0F, 1.0F)
        || !IsFiniteRange(parameters.depth_edge_threshold, 0.005F, 0.5F)
        || !IsFiniteRange(parameters.vertex_tint_gamma, 0.25F, 2.5F)
        || !IsFiniteRange(parameters.distant_highlight_compression, 0.0F, 1.0F)
        || !IsFiniteRange(parameters.feature_outline_width, 0.5F, 3.0F)) {
        return false;
    }
    if (!(parameters.band_thresholds[0] > 0.0F
            && parameters.band_thresholds[0] < parameters.band_thresholds[1]
            && parameters.band_thresholds[1] < parameters.band_thresholds[2]
            && parameters.band_thresholds[2] < 1.0F)) {
        return false;
    }
    return std::all_of(
        parameters.band_colors.begin(),
        parameters.band_colors.end(),
        [](const std::array<float, 3U>& color) { return IsColor(color); }
    );
}

GraphicsParameters GraphicsParametersFromControlBlock(
    const GraphicsControlBlockV1& block
) noexcept {
    GraphicsParameters parameters{};
    parameters.flags = block.flags;
    parameters.dark_scene_outline = {
        block.dark_scene_outline_red,
        block.dark_scene_outline_green,
        block.dark_scene_outline_blue,
    };
    parameters.dark_scene_outline_strength = block.dark_scene_outline_strength;
    parameters.bright_scene_ink_alpha = block.bright_scene_ink_alpha;
    parameters.depth_edge_threshold = block.depth_edge_threshold;
    parameters.band_thresholds = {
        block.band_threshold_0,
        block.band_threshold_1,
        block.band_threshold_2,
    };
    parameters.band_colors = {{
        {block.band_color_0_red, block.band_color_0_green, block.band_color_0_blue},
        {block.band_color_1_red, block.band_color_1_green, block.band_color_1_blue},
        {block.band_color_2_red, block.band_color_2_green, block.band_color_2_blue},
        {block.band_color_3_red, block.band_color_3_green, block.band_color_3_blue},
    }};
    parameters.vertex_tint_gamma = block.vertex_tint_gamma;
    parameters.distant_highlight_compression = block.distant_highlight_compression;
    parameters.feature_outline_width = block.feature_outline_width;
    return parameters;
}

void PopulateGraphicsControlBlock(
    GraphicsControlBlockV1* const block,
    const GraphicsParameters& parameters,
    const DWORD process_id,
    const std::uint64_t process_creation_filetime_utc
) noexcept {
    if (block == nullptr) {
        return;
    }
    *block = {};
    block->magic = kGraphicsControlMagic;
    block->schema_version = kGraphicsControlSchemaVersion;
    block->structure_size = sizeof(GraphicsControlBlockV1);
    block->process_id = process_id;
    block->process_creation_filetime_low = static_cast<std::uint32_t>(
        process_creation_filetime_utc & 0xFFFFFFFFULL
    );
    block->process_creation_filetime_high = static_cast<std::uint32_t>(
        process_creation_filetime_utc >> 32U
    );
    block->flags = parameters.flags;
    block->dark_scene_outline_red = parameters.dark_scene_outline[0];
    block->dark_scene_outline_green = parameters.dark_scene_outline[1];
    block->dark_scene_outline_blue = parameters.dark_scene_outline[2];
    block->dark_scene_outline_strength = parameters.dark_scene_outline_strength;
    block->bright_scene_ink_alpha = parameters.bright_scene_ink_alpha;
    block->depth_edge_threshold = parameters.depth_edge_threshold;
    block->band_threshold_0 = parameters.band_thresholds[0];
    block->band_threshold_1 = parameters.band_thresholds[1];
    block->band_threshold_2 = parameters.band_thresholds[2];
    block->band_color_0_red = parameters.band_colors[0][0];
    block->band_color_0_green = parameters.band_colors[0][1];
    block->band_color_0_blue = parameters.band_colors[0][2];
    block->band_color_1_red = parameters.band_colors[1][0];
    block->band_color_1_green = parameters.band_colors[1][1];
    block->band_color_1_blue = parameters.band_colors[1][2];
    block->band_color_2_red = parameters.band_colors[2][0];
    block->band_color_2_green = parameters.band_colors[2][1];
    block->band_color_2_blue = parameters.band_colors[2][2];
    block->band_color_3_red = parameters.band_colors[3][0];
    block->band_color_3_green = parameters.band_colors[3][1];
    block->band_color_3_blue = parameters.band_colors[3][2];
    block->vertex_tint_gamma = parameters.vertex_tint_gamma;
    block->distant_highlight_compression = parameters.distant_highlight_compression;
    block->feature_outline_width = parameters.feature_outline_width;
    block->desired_sequence = 2;
    block->applied_sequence = 2;
    block->rejected_sequence = 0;
    block->last_error = ERROR_SUCCESS;
}

DWORD StartGraphicsControl() noexcept {
    if (g_mapping != nullptr || g_control != nullptr) {
        return ERROR_ALREADY_INITIALIZED;
    }
    FILETIME creation_time{};
    FILETIME exit_time{};
    FILETIME kernel_time{};
    FILETIME user_time{};
    if (GetProcessTimes(
            GetCurrentProcess(),
            &creation_time,
            &exit_time,
            &kernel_time,
            &user_time
        ) == FALSE) {
        return GetLastError();
    }
    const DWORD process_id = GetCurrentProcessId();
    const std::uint64_t creation_value = FileTimeValue(creation_time);
    const HRESULT name_result = StringCchPrintfW(
        g_control_name,
        std::size(g_control_name),
        kControlNameFormat,
        static_cast<unsigned long>(process_id),
        static_cast<unsigned long long>(creation_value)
    );
    if (FAILED(name_result)) {
        g_control_name[0] = L'\0';
        return ERROR_INSUFFICIENT_BUFFER;
    }
    g_mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0U,
        sizeof(GraphicsControlBlockV1),
        g_control_name
    );
    if (g_mapping == nullptr) {
        const DWORD result = GetLastError();
        g_control_name[0] = L'\0';
        return result;
    }
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(g_mapping);
        g_mapping = nullptr;
        g_control_name[0] = L'\0';
        return ERROR_ALREADY_EXISTS;
    }
    g_control = static_cast<GraphicsControlBlockV1*>(MapViewOfFile(
        g_mapping,
        FILE_MAP_ALL_ACCESS,
        0U,
        0U,
        sizeof(GraphicsControlBlockV1)
    ));
    if (g_control == nullptr) {
        const DWORD result = GetLastError();
        CloseHandle(g_mapping);
        g_mapping = nullptr;
        g_control_name[0] = L'\0';
        return result;
    }
    const GraphicsParameters defaults = DefaultGraphicsParameters();
    g_parameter_snapshots = {defaults, defaults};
    InterlockedExchange(&g_active_parameter_snapshot, 0);
    InterlockedIncrement(&g_parameter_revision);
    PopulateGraphicsControlBlock(g_control, defaults, process_id, creation_value);
    return ERROR_SUCCESS;
}

void ApplyPendingGraphicsControl() noexcept {
    GraphicsControlBlockV1* const block = g_control;
    if (block == nullptr) {
        return;
    }
    const LONG sequence = InterlockedCompareExchange(&block->desired_sequence, 0, 0);
    if (sequence <= 0 || (sequence & 1) != 0
        || sequence == InterlockedCompareExchange(&block->applied_sequence, 0, 0)
        || sequence == InterlockedCompareExchange(&block->rejected_sequence, 0, 0)) {
        return;
    }
    MemoryBarrier();
    const GraphicsControlBlockV1 snapshot = *block;
    MemoryBarrier();
    if (sequence != InterlockedCompareExchange(&block->desired_sequence, 0, 0)) {
        return;
    }
    const std::uint64_t creation_value =
        static_cast<std::uint64_t>(snapshot.process_creation_filetime_low)
        | (static_cast<std::uint64_t>(snapshot.process_creation_filetime_high) << 32U);
    FILETIME creation_time{};
    FILETIME exit_time{};
    FILETIME kernel_time{};
    FILETIME user_time{};
    DWORD error = ERROR_SUCCESS;
    if (snapshot.magic != kGraphicsControlMagic
        || snapshot.schema_version != kGraphicsControlSchemaVersion
        || snapshot.structure_size != sizeof(GraphicsControlBlockV1)
        || snapshot.process_id != GetCurrentProcessId()
        || GetProcessTimes(
            GetCurrentProcess(),
            &creation_time,
            &exit_time,
            &kernel_time,
            &user_time
        ) == FALSE
        || creation_value != FileTimeValue(creation_time)) {
        error = ERROR_REVISION_MISMATCH;
    }
    const GraphicsParameters parameters = GraphicsParametersFromControlBlock(snapshot);
    if (error == ERROR_SUCCESS && !ValidateGraphicsParameters(parameters)) {
        error = ERROR_INVALID_DATA;
    }
    if (error != ERROR_SUCCESS) {
        InterlockedExchange(&block->last_error, static_cast<LONG>(error));
        InterlockedExchange(&block->rejected_sequence, sequence);
        return;
    }
    PublishParameters(parameters);
    InterlockedExchange(&block->last_error, ERROR_SUCCESS);
    InterlockedExchange(&block->applied_sequence, sequence);
}

GraphicsParameters CurrentGraphicsParameters() noexcept {
    const LONG active = InterlockedCompareExchange(&g_active_parameter_snapshot, 0, 0);
    return g_parameter_snapshots[static_cast<std::size_t>(active == 0 ? 0 : 1)];
}

std::uint32_t CurrentGraphicsParametersRevision() noexcept {
    return static_cast<std::uint32_t>(
        InterlockedCompareExchange(&g_parameter_revision, 0, 0)
    );
}

void StopGraphicsControl() noexcept {
    GraphicsControlBlockV1* const block = g_control;
    g_control = nullptr;
    if (block != nullptr) {
        UnmapViewOfFile(block);
    }
    const HANDLE mapping = g_mapping;
    g_mapping = nullptr;
    if (mapping != nullptr) {
        CloseHandle(mapping);
    }
    g_control_name[0] = L'\0';
    const GraphicsParameters defaults = DefaultGraphicsParameters();
    g_parameter_snapshots = {defaults, defaults};
    InterlockedExchange(&g_active_parameter_snapshot, 0);
    InterlockedIncrement(&g_parameter_revision);
}

DWORD GetGraphicsControlName(
    wchar_t* const destination,
    const std::size_t destination_capacity
) noexcept {
    if (destination == nullptr || destination_capacity == 0U) {
        return ERROR_INVALID_PARAMETER;
    }
    const HRESULT result = StringCchCopyW(
        destination,
        destination_capacity,
        g_control_name
    );
    return SUCCEEDED(result) ? ERROR_SUCCESS : ERROR_INSUFFICIENT_BUFFER;
}

GraphicsControlStatus GetGraphicsControlStatus() noexcept {
    GraphicsControlStatus status{};
    GraphicsControlBlockV1* const block = g_control;
    if (block == nullptr || g_mapping == nullptr || g_control_name[0] == L'\0') {
        return status;
    }
    const HRESULT name_result = StringCchCopyW(
        status.mapping_name,
        std::size(status.mapping_name),
        g_control_name
    );
    if (FAILED(name_result)) {
        return {};
    }
    status.desired_sequence = InterlockedCompareExchange(
        &block->desired_sequence, 0, 0
    );
    status.applied_sequence = InterlockedCompareExchange(
        &block->applied_sequence, 0, 0
    );
    status.rejected_sequence = InterlockedCompareExchange(
        &block->rejected_sequence, 0, 0
    );
    status.last_error = static_cast<DWORD>(InterlockedCompareExchange(
        &block->last_error, 0, 0
    ));
    status.available = true;
    return status;
}

}  // namespace wonderbane::extension
