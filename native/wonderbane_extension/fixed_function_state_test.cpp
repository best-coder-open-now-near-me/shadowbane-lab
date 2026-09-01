#include "fixed_function_state.h"

#include <cstdio>

namespace {

int Fail(const char* const message) noexcept {
    std::fprintf(stderr, "%s\n", message);
    return 1;
}

}  // namespace

int main() {
    using namespace wonderbane::extension;
    FixedFunctionStateMirror mirror{};
    SetFixedFunctionCapability(
        &mirror, FixedFunctionCapability::blend, true
    );
    SetFixedFunctionDepthWrites(&mirror, true);
    if (mirror.valid || mirror.blend_enabled || mirror.depth_writes) {
        return Fail("invalid mirrors must ignore incremental transitions");
    }
    AdoptFixedFunctionState(
        &mirror, true, true, true, false, false, true, false
    );
    if (!mirror.valid || !mirror.depth_writes || !mirror.depth_test_enabled
        || !mirror.texture_enabled || mirror.alpha_test_enabled
        || mirror.blend_enabled || !mirror.lighting_enabled
        || mirror.fog_enabled) {
        return Fail("adopted fixed-function snapshot is incorrect");
    }
    SetFixedFunctionCapability(
        &mirror, FixedFunctionCapability::alpha_test, true
    );
    SetFixedFunctionCapability(
        &mirror, FixedFunctionCapability::blend, true
    );
    SetFixedFunctionCapability(
        &mirror, FixedFunctionCapability::lighting, false
    );
    SetFixedFunctionDepthWrites(&mirror, false);
    if (!mirror.alpha_test_enabled || !mirror.blend_enabled
        || mirror.lighting_enabled || mirror.depth_writes) {
        return Fail("incremental fixed-function transitions are incorrect");
    }
    InvalidateFixedFunctionState(&mirror);
    if (mirror.valid) {
        return Fail("fixed-function invalidation failed");
    }
    SetFixedFunctionCapability(
        &mirror, FixedFunctionCapability::fog, true
    );
    if (mirror.fog_enabled) {
        return Fail("invalid mirror accepted a transition");
    }
    return 0;
}
