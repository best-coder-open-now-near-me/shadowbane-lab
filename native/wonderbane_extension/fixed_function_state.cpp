#include "fixed_function_state.h"

namespace wonderbane::extension {

void AdoptFixedFunctionState(
    FixedFunctionStateMirror* const mirror,
    const bool depth_writes,
    const bool depth_test_enabled,
    const bool texture_enabled,
    const bool alpha_test_enabled,
    const bool blend_enabled,
    const bool lighting_enabled,
    const bool fog_enabled
) noexcept {
    if (mirror == nullptr) {
        return;
    }
    *mirror = {
        true,
        depth_writes,
        depth_test_enabled,
        texture_enabled,
        alpha_test_enabled,
        blend_enabled,
        lighting_enabled,
        fog_enabled,
    };
}

void SetFixedFunctionCapability(
    FixedFunctionStateMirror* const mirror,
    const FixedFunctionCapability capability,
    const bool enabled
) noexcept {
    if (mirror == nullptr || !mirror->valid) {
        return;
    }
    switch (capability) {
        case FixedFunctionCapability::depth_test:
            mirror->depth_test_enabled = enabled;
            return;
        case FixedFunctionCapability::texture_2d:
            mirror->texture_enabled = enabled;
            return;
        case FixedFunctionCapability::alpha_test:
            mirror->alpha_test_enabled = enabled;
            return;
        case FixedFunctionCapability::blend:
            mirror->blend_enabled = enabled;
            return;
        case FixedFunctionCapability::lighting:
            mirror->lighting_enabled = enabled;
            return;
        case FixedFunctionCapability::fog:
            mirror->fog_enabled = enabled;
            return;
    }
}

void SetFixedFunctionDepthWrites(
    FixedFunctionStateMirror* const mirror,
    const bool enabled
) noexcept {
    if (mirror != nullptr && mirror->valid) {
        mirror->depth_writes = enabled;
    }
}

void InvalidateFixedFunctionState(
    FixedFunctionStateMirror* const mirror
) noexcept {
    if (mirror != nullptr) {
        mirror->valid = false;
    }
}

}  // namespace wonderbane::extension
