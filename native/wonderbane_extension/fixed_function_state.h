#pragma once

#include <cstdint>

namespace wonderbane::extension {

enum class FixedFunctionCapability : std::uint8_t {
    depth_test,
    texture_2d,
    alpha_test,
    blend,
    lighting,
    fog,
};

struct FixedFunctionStateMirror {
    bool valid = false;
    bool depth_writes = false;
    bool depth_test_enabled = false;
    bool texture_enabled = false;
    bool alpha_test_enabled = false;
    bool blend_enabled = false;
    bool lighting_enabled = false;
    bool fog_enabled = false;
};

void AdoptFixedFunctionState(
    FixedFunctionStateMirror* mirror,
    bool depth_writes,
    bool depth_test_enabled,
    bool texture_enabled,
    bool alpha_test_enabled,
    bool blend_enabled,
    bool lighting_enabled,
    bool fog_enabled
) noexcept;
void SetFixedFunctionCapability(
    FixedFunctionStateMirror* mirror,
    FixedFunctionCapability capability,
    bool enabled
) noexcept;
void SetFixedFunctionDepthWrites(
    FixedFunctionStateMirror* mirror,
    bool enabled
) noexcept;
void InvalidateFixedFunctionState(FixedFunctionStateMirror* mirror) noexcept;

}  // namespace wonderbane::extension
