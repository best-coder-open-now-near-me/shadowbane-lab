#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace wonderbane::extension::terrain_material {

// Pure coverage policy. This layer owns no client pointers, allocations,
// archives, images, textures, or renderer state. The runtime adapter must supply
// one complete, bounded preorder region tree and exact registrations for the
// requested WORLD terrain token.
constexpr std::size_t kMaximumRegions = 4096U;
constexpr std::size_t kMaximumLayers = 32U;
constexpr std::size_t kMaximumDepth = 32U;
constexpr std::size_t kNoParent = static_cast<std::size_t>(-1);

struct Token {
    std::uint32_t resource = 0U;
    std::uint32_t group = 0U;

    bool operator==(const Token&) const = default;
    [[nodiscard]] bool Empty() const noexcept {
        return resource == 0U && group == 0U;
    }
};

struct Layer {
    Token color;
    Token mask;

    bool operator==(const Layer&) const = default;
};

struct Region {
    // Stable identity supplied by the adapter. In the live adapter this is the
    // reviewed region-instance address widened to 64 bits.
    std::uint64_t identity = 0U;
    std::size_t parent = kNoParent;

    // Canonical clockwise quarter turns from the reviewed registration
    // transform. Arbitrary rotations are unsupported.
    std::uint8_t rotation = 0U;

    // False for custom base replacements or any mode whose composition
    // semantics have not been reviewed as ordinary material-only layers.
    bool material_only = true;

    // Exact ordered color/mask registrations for the requested terrain key.
    std::span<const Layer> registered_layers;
};

enum class Decision : std::uint8_t {
    unchanged,
    append,
    invalid_input,
    ambiguous_regions,
    incompatible_rotation,
    unsupported_material_mode,
    partial_or_reordered_stack,
    layer_capacity,
};

struct Plan {
    Decision decision = Decision::unchanged;
    std::array<Layer, kMaximumLayers> additions{};
    std::array<std::size_t, kMaximumDepth> regions{};
    std::size_t layer_count = 0U;
    std::size_t region_count = 0U;
};

// existing is the complete UNPRUNED builder stack. Generated masks may have an
// empty token. Registration tokens may not. Retained draw-layer indices are not
// usable here because the client later prunes zero and fully occluded masks.
//
// A rejected result is always non-actionable: layer_count and region_count are
// zero and the fixed buffers remain value-initialized.
[[nodiscard]] Plan PlanCoverage(
    std::span<const Region> regions,
    std::size_t material_owner,
    std::span<const Layer> existing,
    std::uint8_t source_rotation) noexcept;

}  // namespace wonderbane::extension::terrain_material
