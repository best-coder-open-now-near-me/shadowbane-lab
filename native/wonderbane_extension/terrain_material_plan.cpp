#include "terrain_material_plan.h"

#include <algorithm>
#include <array>

namespace wonderbane::extension::terrain_material {
namespace {

[[nodiscard]] Plan Reject(const Decision reason) noexcept {
    Plan result;
    result.decision = reason;
    return result;
}

[[nodiscard]] bool DescendsFrom(
    const std::span<const Region> regions,
    std::size_t child,
    const std::size_t ancestor) noexcept {
    for (std::size_t depth = 0U;
         child != kNoParent && depth < kMaximumDepth;
         ++depth) {
        if (child == ancestor) {
            return true;
        }
        child = regions[child].parent;
    }
    return false;
}

[[nodiscard]] bool HasUniqueRegisteredMasks(
    const std::span<const Layer> layers) noexcept {
    for (std::size_t index = 0U; index < layers.size(); ++index) {
        if (layers[index].color.Empty() || layers[index].mask.Empty()) {
            return false;
        }
        for (std::size_t previous = 0U; previous < index; ++previous) {
            if (layers[previous].mask == layers[index].mask) {
                return false;
            }
        }
    }
    return true;
}

// Verify every promise the live adapter relies on: one rooted tree, unique
// identities, bounded depth, and true preorder traversal. Merely requiring
// parent < child is insufficient because a descendant could otherwise appear
// after traversal has already moved to a sibling subtree.
[[nodiscard]] bool ValidTree(const std::span<const Region> regions) noexcept {
    if (regions.empty() || regions.size() > kMaximumRegions) {
        return false;
    }

    std::array<std::size_t, kMaximumDepth> active_ancestry{};
    std::size_t active_count = 0U;

    for (std::size_t index = 0U; index < regions.size(); ++index) {
        const auto& region = regions[index];
        if (region.identity == 0U || region.rotation > 3U ||
            region.registered_layers.size() > kMaximumLayers ||
            !HasUniqueRegisteredMasks(region.registered_layers)) {
            return false;
        }

        for (std::size_t previous = 0U; previous < index; ++previous) {
            if (regions[previous].identity == region.identity) {
                return false;
            }
        }

        if (index == 0U) {
            if (region.parent != kNoParent) {
                return false;
            }
            active_ancestry[0] = 0U;
            active_count = 1U;
            continue;
        }

        if (region.parent == kNoParent || region.parent >= index) {
            return false;
        }

        const auto parent_position = std::find(
            active_ancestry.begin(),
            active_ancestry.begin() + active_count,
            region.parent);
        if (parent_position == active_ancestry.begin() + active_count) {
            return false;
        }

        const auto depth = static_cast<std::size_t>(
            parent_position - active_ancestry.begin()) + 1U;
        if (depth >= kMaximumDepth) {
            return false;
        }
        active_ancestry[depth] = index;
        active_count = depth + 1U;
    }

    return true;
}

enum class StackMatch : std::uint8_t {
    absent,
    complete,
    partial,
};

[[nodiscard]] StackMatch MatchStack(
    const std::span<const Layer> existing,
    const std::span<const Layer> registered) noexcept {
    if (registered.empty()) {
        return StackMatch::complete;
    }

    bool overlap = false;
    for (const auto& registered_layer : registered) {
        std::size_t mask_matches = 0U;
        bool exact_match = false;
        for (const auto& existing_layer : existing) {
            if (existing_layer.mask == registered_layer.mask) {
                overlap = true;
                ++mask_matches;
                exact_match = exact_match || existing_layer == registered_layer;
            }
        }
        // A repeated mask, or the right mask paired with another color, makes
        // the current stack unsafe to extend.
        if (mask_matches > 1U || (mask_matches == 1U && !exact_match)) {
            return StackMatch::partial;
        }
    }

    if (!overlap) {
        return StackMatch::absent;
    }
    if (registered.size() > existing.size()) {
        return StackMatch::partial;
    }

    std::size_t complete_runs = 0U;
    for (std::size_t offset = 0U;
         offset <= existing.size() - registered.size();
         ++offset) {
        if (std::equal(
                registered.begin(),
                registered.end(),
                existing.begin() + static_cast<std::ptrdiff_t>(offset))) {
            ++complete_runs;
        }
    }
    if (complete_runs != 1U) {
        return StackMatch::partial;
    }

    // Every registered mask is unique by ValidTree. A complete run is valid
    // only when each mask occurs exactly once in the entire existing stack.
    for (const auto& registered_layer : registered) {
        const auto occurrences = std::count_if(
            existing.begin(),
            existing.end(),
            [&registered_layer](const Layer& item) {
                return item.mask == registered_layer.mask;
            });
        if (occurrences != 1) {
            return StackMatch::partial;
        }
    }
    return StackMatch::complete;
}

}  // namespace

Plan PlanCoverage(
    const std::span<const Region> regions,
    const std::size_t material_owner,
    const std::span<const Layer> existing,
    const std::uint8_t source_rotation) noexcept {
    if (!ValidTree(regions) || material_owner >= regions.size() ||
        source_rotation > 3U) {
        return Reject(Decision::invalid_input);
    }
    if (existing.size() > kMaximumLayers) {
        return Reject(Decision::layer_capacity);
    }
    if (!regions[material_owner].material_only) {
        return Reject(Decision::unsupported_material_mode);
    }

    Plan plan;
    std::size_t deepest_candidate = material_owner;

    for (std::size_t index = 0U; index < regions.size(); ++index) {
        const auto& region = regions[index];
        if (index == material_owner || region.registered_layers.empty() ||
            !DescendsFrom(regions, index, material_owner)) {
            continue;
        }

        // Registrations on separate descendant branches cannot be ordered by
        // traversal position. Fail closed rather than choosing a sibling.
        if (!DescendsFrom(regions, index, deepest_candidate)) {
            return Reject(Decision::ambiguous_regions);
        }
        deepest_candidate = index;

        if (!region.material_only) {
            return Reject(Decision::unsupported_material_mode);
        }
        if (region.rotation != source_rotation) {
            return Reject(Decision::incompatible_rotation);
        }

        const auto current_match = MatchStack(existing, region.registered_layers);
        if (current_match == StackMatch::partial) {
            return Reject(Decision::partial_or_reordered_stack);
        }
        if (current_match == StackMatch::complete) {
            continue;
        }

        // Appending a missing parent below an already-published child reverses
        // the reviewed parent-before-child composition order.
        for (std::size_t child = index + 1U; child < regions.size(); ++child) {
            if (!regions[child].registered_layers.empty() &&
                DescendsFrom(regions, child, index) &&
                MatchStack(existing, regions[child].registered_layers) !=
                    StackMatch::absent) {
                return Reject(Decision::partial_or_reordered_stack);
            }
        }

        const auto planned = std::span<const Layer>(
            plan.additions.data(), plan.layer_count);
        if (MatchStack(planned, region.registered_layers) != StackMatch::absent) {
            return Reject(Decision::partial_or_reordered_stack);
        }

        if (plan.region_count >= plan.regions.size() ||
            region.registered_layers.size() >
                kMaximumLayers - existing.size() - plan.layer_count) {
            return Reject(Decision::layer_capacity);
        }

        plan.regions[plan.region_count++] = index;
        for (const auto& layer : region.registered_layers) {
            plan.additions[plan.layer_count++] = layer;
        }
    }

    if (plan.layer_count != 0U) {
        plan.decision = Decision::append;
    }
    return plan;
}

}  // namespace wonderbane::extension::terrain_material
