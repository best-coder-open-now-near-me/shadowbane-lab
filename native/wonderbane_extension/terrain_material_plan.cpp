#include "terrain_material_plan.h"

#include <algorithm>

namespace wonderbane::extension::terrain_material {
namespace {

Plan Reject(const Decision reason) noexcept {
    Plan result;
    result.decision = reason;
    return result;  // Never return a partially actionable plan on rejection.
}

bool DescendsFrom(const std::span<const Region> regions, std::size_t child,
    const std::size_t ancestor) noexcept {
    for (std::size_t depth = 0U; child != kNoParent && depth < kMaximumDepth; ++depth) {
        if (child == ancestor) { return true; }
        child = regions[child].parent;
    }
    return false;
}

bool ValidTree(const std::span<const Region> regions) noexcept {
    if (regions.empty() || regions.size() > kMaximumRegions) { return false; }
    for (std::size_t index = 0U; index < regions.size(); ++index) {
        const auto& region = regions[index];
        if (region.identity == 0U || region.rotation > 3U
            || region.registered_layers.size() > kMaximumLayers
            || (index == 0U ? region.parent != kNoParent : region.parent >= index)) {
            return false;
        }
        // Native adapters reject repeated pointers while walking. Keep that
        // invariant explicit here too: the same instance cannot have two owners.
        for (std::size_t previous = 0U; previous < index; ++previous) {
            if (regions[previous].identity == region.identity) { return false; }
        }
        std::size_t depth = 0U;
        for (auto ancestor = index; ancestor != kNoParent; ancestor = regions[ancestor].parent) {
            if (++depth > kMaximumDepth) { return false; }
        }
        for (const auto& layer : region.registered_layers) {
            if (layer.color.Empty() || layer.mask.Empty()) { return false; }
        }
    }
    return true;
}

enum class StackMatch { absent, complete, partial };
StackMatch MatchStack(const std::span<const Layer> existing,
    const std::span<const Layer> registered) noexcept {
    if (registered.empty()) { return StackMatch::complete; }
    // A duplicate mask under another color is also a conflict. Appending it
    // would silently change composition, not merely restore missing coverage.
    bool overlap = false;
    for (const auto& layer : registered) {
        overlap = overlap || std::any_of(existing.begin(), existing.end(),
            [&layer](const Layer& item) { return item.mask == layer.mask; });
    }
    if (!overlap) { return StackMatch::absent; }
    if (registered.size() > existing.size()) { return StackMatch::partial; }
    std::size_t matches = 0U;
    for (std::size_t offset = 0U; offset <= existing.size() - registered.size(); ++offset) {
        if (std::equal(registered.begin(), registered.end(), existing.begin() + offset)) {
            ++matches;
        }
    }
    if (matches != 1U) { return StackMatch::partial; }
    // Reject additional copies outside the complete run as well.
    for (const auto& layer : registered) {
        const auto in_existing = std::count_if(existing.begin(), existing.end(),
            [&layer](const Layer& item) { return item.mask == layer.mask; });
        const auto in_registered = std::count_if(registered.begin(), registered.end(),
            [&layer](const Layer& item) { return item.mask == layer.mask; });
        if (in_existing != in_registered) { return StackMatch::partial; }
    }
    return StackMatch::complete;
}

}  // namespace

Plan PlanCoverage(const std::span<const Region> regions, const std::size_t material_owner,
    const std::span<const Layer> existing, const std::uint8_t source_rotation) noexcept {
    if (!ValidTree(regions) || material_owner >= regions.size() || source_rotation > 3U) {
        return Reject(Decision::invalid_input);
    }
    if (existing.size() > kMaximumLayers) { return Reject(Decision::layer_capacity); }
    Plan plan;
    std::size_t deepest = material_owner;
    for (std::size_t index = 0U; index < regions.size(); ++index) {
        const auto& region = regions[index];
        if (index == material_owner || region.registered_layers.empty()
            || !DescendsFrom(regions, index, material_owner)) { continue; }
        // Never decide between sibling regions using traversal order. A single
        // terrain source has one mask rotation; overlapping branches need an
        // explicitly reviewed composition policy before they can be repaired.
        if (!DescendsFrom(regions, index, deepest)) {
            return Reject(Decision::ambiguous_regions);
        }
        deepest = index;
        if (!region.material_only) { return Reject(Decision::unsupported_material_mode); }
        if (region.rotation != source_rotation) {
            return Reject(Decision::incompatible_rotation);
        }
        const auto match = MatchStack(existing, region.registered_layers);
        if (match == StackMatch::partial) { return Reject(Decision::partial_or_reordered_stack); }
        if (match == StackMatch::complete) { continue; }
        // Every parent layer must remain below its child's layers. If a child
        // was already present, appending a missing parent afterward is invalid.
        for (std::size_t child = index + 1U; child < regions.size(); ++child) {
            if (DescendsFrom(regions, child, index)
                && !regions[child].registered_layers.empty()
                && MatchStack(existing, regions[child].registered_layers) != StackMatch::absent) {
                return Reject(Decision::partial_or_reordered_stack);
            }
        }
        if (MatchStack(std::span(plan.additions).first(plan.layer_count),
                region.registered_layers) != StackMatch::absent) {
            return Reject(Decision::partial_or_reordered_stack);
        }
        if (region.registered_layers.size() > kMaximumLayers - existing.size() - plan.layer_count
            || plan.region_count == plan.regions.size()) { return Reject(Decision::layer_capacity); }
        plan.regions[plan.region_count++] = index;
        for (const auto& layer : region.registered_layers) {
            plan.additions[plan.layer_count++] = layer;
        }
    }
    if (plan.layer_count != 0U) { plan.decision = Decision::append; }
    return plan;
}

}  // namespace wonderbane::extension::terrain_material
