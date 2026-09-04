#include "terrain_material_plan.h"

#include <array>
#include <cstdlib>
#include <iostream>
#include <span>
#include <string_view>

namespace terrain = wonderbane::extension::terrain_material;

namespace {

[[noreturn]] void Fail(const std::string_view message) {
    std::cerr << "terrain_material_plan_test: " << message << '\n';
    std::exit(EXIT_FAILURE);
}

void Expect(const bool condition, const std::string_view message) {
    if (!condition) {
        Fail(message);
    }
}

constexpr terrain::Token Token(
    const std::uint32_t resource,
    const std::uint32_t group = 1U) {
    return terrain::Token{resource, group};
}

constexpr terrain::Layer Layer(
    const std::uint32_t color,
    const std::uint32_t mask) {
    return terrain::Layer{Token(color), Token(mask)};
}

terrain::Region Region(
    const std::uint64_t identity,
    const std::size_t parent,
    const std::span<const terrain::Layer> layers = {},
    const std::uint8_t rotation = 0U,
    const bool material_only = true) {
    return terrain::Region{identity, parent, rotation, material_only, layers};
}

void ExpectRejected(const terrain::Plan& plan, const terrain::Decision reason) {
    Expect(plan.decision == reason, "unexpected rejection reason");
    Expect(plan.layer_count == 0U, "rejection leaked actionable layers");
    Expect(plan.region_count == 0U, "rejection leaked actionable regions");
    for (const auto& addition : plan.additions) {
        Expect(addition.color.Empty(), "rejection did not clear color token");
        Expect(addition.mask.Empty(), "rejection did not clear mask token");
    }
}

void TestAppendsOneMissingDescendantStack() {
    constexpr std::array child_layers{Layer(100U, 200U), Layer(101U, 201U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, child_layers),
    };

    const auto plan = terrain::PlanCoverage(regions, 0U, {}, 0U);
    Expect(plan.decision == terrain::Decision::append, "missing child stack not appended");
    Expect(plan.region_count == 1U && plan.regions[0] == 1U,
        "wrong contributing region");
    Expect(plan.layer_count == child_layers.size(), "wrong addition count");
    Expect(std::equal(child_layers.begin(), child_layers.end(), plan.additions.begin()),
        "addition order changed");
}

void TestPreservesACompleteStack() {
    constexpr std::array child_layers{Layer(100U, 200U), Layer(101U, 201U)};
    constexpr std::array existing{
        terrain::Layer{terrain::Token{}, terrain::Token{}},
        child_layers[0],
        child_layers[1],
        Layer(900U, 901U),
    };
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, child_layers),
    };

    const auto plan = terrain::PlanCoverage(regions, 0U, existing, 0U);
    Expect(plan.decision == terrain::Decision::unchanged, "complete stack was not preserved");
    Expect(plan.layer_count == 0U && plan.region_count == 0U,
        "unchanged result contained additions");
}

void TestRejectsPartialAndReorderedStacks() {
    constexpr std::array child_layers{Layer(100U, 200U), Layer(101U, 201U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, child_layers),
    };

    constexpr std::array partial{child_layers[0]};
    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, partial, 0U),
        terrain::Decision::partial_or_reordered_stack);

    constexpr std::array reordered{child_layers[1], child_layers[0]};
    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, reordered, 0U),
        terrain::Decision::partial_or_reordered_stack);

    constexpr std::array wrong_color{
        terrain::Layer{Token(777U), child_layers[0].mask},
    };
    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, wrong_color, 0U),
        terrain::Decision::partial_or_reordered_stack);

    constexpr std::array duplicate{child_layers[0], child_layers[1], child_layers[0]};
    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, duplicate, 0U),
        terrain::Decision::partial_or_reordered_stack);
}

void TestAppendsNestedStacksInParentChildOrder() {
    constexpr std::array parent_layers{Layer(100U, 200U)};
    constexpr std::array child_layers{Layer(101U, 201U), Layer(102U, 202U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, parent_layers),
        Region(3U, 1U, child_layers),
    };

    const auto plan = terrain::PlanCoverage(regions, 0U, {}, 0U);
    Expect(plan.decision == terrain::Decision::append, "nested stack not appended");
    Expect(plan.region_count == 2U, "nested contributing regions lost");
    Expect(plan.regions[0] == 1U && plan.regions[1] == 2U,
        "nested region order changed");
    Expect(plan.layer_count == 3U, "nested layer count changed");
    Expect(plan.additions[0] == parent_layers[0] &&
            plan.additions[1] == child_layers[0] &&
            plan.additions[2] == child_layers[1],
        "nested material order changed");
}

void TestRejectsMissingParentBelowPublishedChild() {
    constexpr std::array parent_layers{Layer(100U, 200U)};
    constexpr std::array child_layers{Layer(101U, 201U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, parent_layers),
        Region(3U, 1U, child_layers),
    };
    constexpr std::array existing{child_layers[0]};

    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, existing, 0U),
        terrain::Decision::partial_or_reordered_stack);
}

void TestAppendsMissingChildAboveCompleteParent() {
    constexpr std::array parent_layers{Layer(100U, 200U)};
    constexpr std::array child_layers{Layer(101U, 201U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, parent_layers),
        Region(3U, 1U, child_layers),
    };
    constexpr std::array existing{parent_layers[0]};

    const auto plan = terrain::PlanCoverage(regions, 0U, existing, 0U);
    Expect(plan.decision == terrain::Decision::append, "missing child was not appended");
    Expect(plan.region_count == 1U && plan.regions[0] == 2U,
        "wrong child contributor");
    Expect(plan.layer_count == 1U && plan.additions[0] == child_layers[0],
        "wrong child layer");
}

void TestRejectsAmbiguousSiblingRegistrations() {
    constexpr std::array west_layers{Layer(100U, 200U)};
    constexpr std::array east_layers{Layer(101U, 201U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, west_layers),
        Region(3U, 0U, east_layers),
    };

    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, {}, 0U),
        terrain::Decision::ambiguous_regions);
}

void TestRejectsUnsupportedModesAndRotations() {
    constexpr std::array layers{Layer(100U, 200U)};
    const std::array unsupported_owner{
        Region(1U, terrain::kNoParent, {}, 0U, false),
        Region(2U, 0U, layers),
    };
    ExpectRejected(
        terrain::PlanCoverage(unsupported_owner, 0U, {}, 0U),
        terrain::Decision::unsupported_material_mode);

    const std::array unsupported_child{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, layers, 0U, false),
    };
    ExpectRejected(
        terrain::PlanCoverage(unsupported_child, 0U, {}, 0U),
        terrain::Decision::unsupported_material_mode);

    const std::array rotated_child{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, layers, 1U),
    };
    ExpectRejected(
        terrain::PlanCoverage(rotated_child, 0U, {}, 0U),
        terrain::Decision::incompatible_rotation);

    ExpectRejected(
        terrain::PlanCoverage(rotated_child, 0U, {}, 4U),
        terrain::Decision::invalid_input);
}

void TestRejectsInvalidTreesAndRegistrations() {
    constexpr std::array layers{Layer(100U, 200U)};

    const std::array duplicate_identity{
        Region(1U, terrain::kNoParent),
        Region(1U, 0U, layers),
    };
    ExpectRejected(
        terrain::PlanCoverage(duplicate_identity, 0U, {}, 0U),
        terrain::Decision::invalid_input);

    const std::array disconnected{
        Region(1U, terrain::kNoParent),
        Region(2U, terrain::kNoParent, layers),
    };
    ExpectRejected(
        terrain::PlanCoverage(disconnected, 0U, {}, 0U),
        terrain::Decision::invalid_input);

    const std::array non_preorder{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U),
        Region(3U, 0U),
        Region(4U, 1U, layers),
    };
    ExpectRejected(
        terrain::PlanCoverage(non_preorder, 0U, {}, 0U),
        terrain::Decision::invalid_input);

    constexpr std::array duplicate_mask{
        Layer(100U, 200U),
        Layer(101U, 200U),
    };
    const std::array invalid_registration{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, duplicate_mask),
    };
    ExpectRejected(
        terrain::PlanCoverage(invalid_registration, 0U, {}, 0U),
        terrain::Decision::invalid_input);

    constexpr std::array empty_registration{
        terrain::Layer{Token(100U), terrain::Token{}},
    };
    const std::array empty_token{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, empty_registration),
    };
    ExpectRejected(
        terrain::PlanCoverage(empty_token, 0U, {}, 0U),
        terrain::Decision::invalid_input);

    ExpectRejected(
        terrain::PlanCoverage(duplicate_identity, duplicate_identity.size(), {}, 0U),
        terrain::Decision::invalid_input);
}

void TestRejectsTransactionalCapacityOverflow() {
    constexpr std::array layers{Layer(100U, 200U), Layer(101U, 201U)};
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, layers),
    };

    std::array<terrain::Layer, terrain::kMaximumLayers - 1U> existing{};
    for (std::size_t index = 0U; index < existing.size(); ++index) {
        existing[index] = Layer(
            static_cast<std::uint32_t>(1000U + index),
            static_cast<std::uint32_t>(2000U + index));
    }
    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, existing, 0U),
        terrain::Decision::layer_capacity);

    std::array<terrain::Layer, terrain::kMaximumLayers + 1U> oversized{};
    ExpectRejected(
        terrain::PlanCoverage(regions, 0U, oversized, 0U),
        terrain::Decision::layer_capacity);
}

void TestGeneratedExistingLayersDoNotCreateFalseOverlap() {
    constexpr std::array layers{Layer(100U, 200U)};
    constexpr std::array generated{
        terrain::Layer{terrain::Token{}, terrain::Token{}},
    };
    const std::array regions{
        Region(1U, terrain::kNoParent),
        Region(2U, 0U, layers),
    };

    const auto plan = terrain::PlanCoverage(regions, 0U, generated, 0U);
    Expect(plan.decision == terrain::Decision::append,
        "generated layer caused false registration overlap");
    Expect(plan.layer_count == 1U && plan.additions[0] == layers[0],
        "registered layer changed after generated base");
}

}  // namespace

int main() {
    TestAppendsOneMissingDescendantStack();
    TestPreservesACompleteStack();
    TestRejectsPartialAndReorderedStacks();
    TestAppendsNestedStacksInParentChildOrder();
    TestRejectsMissingParentBelowPublishedChild();
    TestAppendsMissingChildAboveCompleteParent();
    TestRejectsAmbiguousSiblingRegistrations();
    TestRejectsUnsupportedModesAndRotations();
    TestRejectsInvalidTreesAndRegistrations();
    TestRejectsTransactionalCapacityOverflow();
    TestGeneratedExistingLayersDoNotCreateFalseOverlap();
    std::cout << "terrain material coverage policy tests passed\n";
    return EXIT_SUCCESS;
}
