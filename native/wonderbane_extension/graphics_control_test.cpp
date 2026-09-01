#include "graphics_control.h"

#include <Windows.h>

#include <cmath>
#include <cstdio>
#include <limits>

namespace {

bool NearlyEqual(const float left, const float right) noexcept {
    return std::fabs(left - right) < 0.0001F;
}

int Fail(const char* const operation) noexcept {
    std::fprintf(stderr, "%s failed\n", operation);
    return 1;
}

}  // namespace

int main() {
    using wonderbane::extension::CurrentGraphicsParameters;
    using wonderbane::extension::DefaultGraphicsParameters;
    using wonderbane::extension::GetGraphicsControlName;
    using wonderbane::extension::GetGraphicsControlStatus;
    using wonderbane::extension::GraphicsControlBlockV1;
    using wonderbane::extension::GraphicsParametersFromControlBlock;
    using wonderbane::extension::PopulateGraphicsControlBlock;
    using wonderbane::extension::StartGraphicsControl;
    using wonderbane::extension::StopGraphicsControl;
    using wonderbane::extension::ValidateGraphicsParameters;

    const auto defaults = DefaultGraphicsParameters();
    if (!ValidateGraphicsParameters(defaults)
        || defaults.depth_edge_threshold != 0.055F
        || defaults.feature_outline_width != 1.35F) {
        return Fail("default parameter contract");
    }
    auto invalid = defaults;
    invalid.depth_edge_threshold = std::numeric_limits<float>::quiet_NaN();
    if (ValidateGraphicsParameters(invalid)) {
        return Fail("non-finite rejection");
    }
    invalid = defaults;
    invalid.band_thresholds = {0.5F, 0.4F, 0.7F};
    if (ValidateGraphicsParameters(invalid)) {
        return Fail("ordered threshold rejection");
    }
    invalid = defaults;
    invalid.flags = 0x80000000U;
    if (ValidateGraphicsParameters(invalid)) {
        return Fail("unknown flag rejection");
    }

    GraphicsControlBlockV1 block{};
    PopulateGraphicsControlBlock(&block, defaults, 1234U, 0x1122334455667788ULL);
    const auto round_trip = GraphicsParametersFromControlBlock(block);
    if (block.magic != wonderbane::extension::kGraphicsControlMagic
        || block.schema_version != 1U || block.structure_size != 256U
        || block.process_creation_filetime_low != 0x55667788U
        || block.process_creation_filetime_high != 0x11223344U
        || block.desired_sequence != 2 || block.applied_sequence != 2
        || !NearlyEqual(
            round_trip.dark_scene_outline[2], defaults.dark_scene_outline[2]
        ) || !NearlyEqual(
            round_trip.band_colors[3][0], defaults.band_colors[3][0]
        )) {
        return Fail("control block layout round trip");
    }

    DWORD result = StartGraphicsControl();
    if (result != ERROR_SUCCESS) {
        return Fail("control mapping start");
    }
    wchar_t name[128U]{};
    result = GetGraphicsControlName(name, std::size(name));
    if (result != ERROR_SUCCESS
        || wcsstr(name, L"Local\\WonderBaneGraphicsControl-") != name) {
        StopGraphicsControl();
        return Fail("exact control mapping name");
    }
    const auto control_status = GetGraphicsControlStatus();
    if (!control_status.available || control_status.desired_sequence != 2
        || control_status.applied_sequence != 2
        || control_status.rejected_sequence != 0
        || control_status.last_error != ERROR_SUCCESS) {
        StopGraphicsControl();
        return Fail("control status snapshot");
    }
    if (!ValidateGraphicsParameters(CurrentGraphicsParameters())) {
        StopGraphicsControl();
        return Fail("published defaults");
    }
    StopGraphicsControl();
    if (GetGraphicsControlStatus().available) {
        return Fail("stopped control status");
    }
    return 0;
}
