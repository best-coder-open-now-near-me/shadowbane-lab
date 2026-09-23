#pragma once

// DRAFT HANDOFF: not connected to the renderer or build targets. Behavioral
// tests, policy review, and the native ownership adapter are still outstanding.

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace wonderbane::extension::terrain_material {

// Policy only: no client pointers, allocations, archive access, or mutations.
// The adapter must supply a complete, bounded, preorder region tree and only
// exact registrations for the requested WORLD terrain token. Geometric
// containment and local archive tile coordinates are not coverage evidence.
constexpr std::size_t kMaximumRegions = 4096U;
constexpr std::size_t kMaximumLayers = 32U;
constexpr std::size_t kMaximumDepth = 32U;
constexpr std::size_t kNoParent = static_cast<std::size_t>(-1);

struct Token {
    std::uint32_t resource = 0U, group = 0U;
    bool operator==(const Token&) const = default;
    bool Empty() const noexcept { return resource == 0U && group == 0U; }
};
struct Layer {
    Token color, mask;
    bool operator==(const Layer&) const = default;
};
struct Region {
    std::uint64_t identity = 0U;
    std::size_t parent = kNoParent;
    // Canonical quarter turns from the reviewed registration transform.
    std::uint8_t rotation = 0U;
    // False for custom base replacements or any unreviewed material mode.
    bool material_only = true;
    std::span<const Layer> registered_layers;
};
enum class Decision {
    unchanged, append, invalid_input, ambiguous_regions,
    incompatible_rotation, unsupported_material_mode, partial_or_reordered_stack,
    layer_capacity
};
struct Plan {
    Decision decision = Decision::unchanged;
    std::array<Layer, kMaximumLayers> additions{};
    std::array<std::size_t, kMaximumDepth> regions{};
    std::size_t layer_count = 0U, region_count = 0U;
};

// Existing layers are the UNPRUNED builder stack. Generated masks may have an
// empty token; registration tokens may not. Retained draw-layer indices are not
// usable here because the client later prunes zero and occluded masks.
Plan PlanCoverage(std::span<const Region> regions, std::size_t material_owner,
    std::span<const Layer> existing, std::uint8_t source_rotation) noexcept;

}  // namespace wonderbane::extension::terrain_material
