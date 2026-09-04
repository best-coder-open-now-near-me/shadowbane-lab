#include "terrain_material_transaction.h"

#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string_view>

namespace terrain = wonderbane::extension::terrain_material;

namespace {

[[noreturn]] void Fail(const std::string_view message) {
    std::cerr << "terrain_material_transaction_test: " << message << '\n';
    std::exit(EXIT_FAILURE);
}

void Expect(const bool condition, const std::string_view message) {
    if (!condition) {
        Fail(message);
    }
}

constexpr terrain::Layer Layer(
    const std::uint32_t color,
    const std::uint32_t mask) {
    return terrain::Layer{
        terrain::Token{color, 1U},
        terrain::Token{mask, 1U}};
}

terrain::Plan AppendPlan(const std::size_t count) {
    terrain::Plan plan;
    plan.decision = terrain::Decision::append;
    plan.region_count = 1U;
    plan.regions[0] = 1U;
    plan.layer_count = count;
    for (std::size_t index = 0U; index < count; ++index) {
        plan.additions[index] = Layer(
            static_cast<std::uint32_t>(100U + index),
            static_cast<std::uint32_t>(200U + index));
    }
    return plan;
}

enum class BadProof {
    none,
    shared_image,
    shared_pixels,
    source_image_alias,
    source_pixels_alias,
    immutable_image,
    zero_bytes,
};

struct FakeContext {
    static constexpr std::size_t never = std::numeric_limits<std::size_t>::max();

    std::size_t prepare_calls = 0U;
    std::size_t release_calls = 0U;
    std::size_t begin_calls = 0U;
    std::size_t append_calls = 0U;
    std::size_t rollback_calls = 0U;
    std::size_t commit_calls = 0U;
    std::size_t quarantine_calls = 0U;

    std::size_t fail_prepare_at = never;
    std::size_t fail_append_at = never;
    std::size_t bad_proof_at = never;
    BadProof bad_proof = BadProof::none;
    bool fail_begin = false;
    bool fail_rollback = false;

    std::size_t color_count = 3U;
    std::size_t mask_count = 3U;
};

bool Prepare(
    void* opaque,
    const terrain::Layer&,
    terrain::PreparedLayer& prepared) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    const auto index = context.prepare_calls++;
    prepared.color_texture = 0x1000U + index;
    prepared.mask_texture = 0x2000U + index;
    prepared.source_image = 0x3000U + index;
    prepared.source_pixels = 0x4000U + index;
    prepared.owned_image = 0x5000U + index;
    prepared.owned_pixels = 0x6000U + index;
    prepared.pixel_bytes = 128U * 128U;
    prepared.owned_image_mutable = true;

    if (index == context.bad_proof_at) {
        switch (context.bad_proof) {
            case BadProof::shared_image:
                prepared.owned_image = 0x5000U;
                break;
            case BadProof::shared_pixels:
                prepared.owned_pixels = 0x6000U;
                break;
            case BadProof::source_image_alias:
                prepared.owned_image = prepared.source_image;
                break;
            case BadProof::source_pixels_alias:
                prepared.owned_pixels = prepared.source_pixels;
                break;
            case BadProof::immutable_image:
                prepared.owned_image_mutable = false;
                break;
            case BadProof::zero_bytes:
                prepared.pixel_bytes = 0U;
                break;
            case BadProof::none:
                break;
        }
    }

    return index != context.fail_prepare_at;
}

void Release(
    void* opaque,
    terrain::PreparedLayer& prepared) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    ++context.release_calls;
    prepared = {};
}

bool Begin(
    void* opaque,
    const std::size_t,
    terrain::PublicationCheckpoint& checkpoint) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    ++context.begin_calls;
    checkpoint.original_color_count = context.color_count;
    checkpoint.original_mask_count = context.mask_count;
    return !context.fail_begin;
}

bool Append(
    void* opaque,
    const terrain::PreparedLayer&) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    const auto index = context.append_calls++;
    ++context.color_count;
    if (index == context.fail_append_at) {
        // Model a failure between paired vector publications. Rollback must
        // remove this unpaired color reference as well.
        return false;
    }
    ++context.mask_count;
    return true;
}

bool Rollback(
    void* opaque,
    const terrain::PublicationCheckpoint& checkpoint) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    ++context.rollback_calls;
    if (context.fail_rollback) {
        return false;
    }
    context.color_count = checkpoint.original_color_count;
    context.mask_count = checkpoint.original_mask_count;
    return true;
}

void Commit(
    void* opaque,
    terrain::PreparedLayer& prepared) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    ++context.commit_calls;
    prepared = {};
}

void Quarantine(
    void* opaque,
    terrain::PreparedLayer& prepared) noexcept {
    auto& context = *static_cast<FakeContext*>(opaque);
    ++context.quarantine_calls;
    prepared = {};
}

terrain::TransactionBackend Backend(FakeContext& context) {
    return terrain::TransactionBackend{
        &context,
        &Prepare,
        &Release,
        &Begin,
        &Append,
        &Rollback,
        &Commit,
        &Quarantine,
    };
}

void TestUnchangedRequiresNoBackend() {
    const terrain::Plan plan;
    const terrain::TransactionBackend backend;
    const auto outcome = terrain::ExecuteTransaction(plan, backend);
    Expect(outcome.result == terrain::TransactionResult::unchanged,
        "unchanged plan was not a no-op");
}

void TestRejectsInvalidPlanAndBackend() {
    FakeContext context;
    auto invalid_plan = AppendPlan(0U);
    const auto invalid = terrain::ExecuteTransaction(invalid_plan, Backend(context));
    Expect(invalid.result == terrain::TransactionResult::invalid_plan,
        "zero-layer append plan accepted");
    Expect(context.prepare_calls == 0U, "invalid plan reached backend");

    const auto plan = AppendPlan(1U);
    terrain::TransactionBackend missing_callback;
    const auto backend_result = terrain::ExecuteTransaction(plan, missing_callback);
    Expect(backend_result.result == terrain::TransactionResult::invalid_backend,
        "incomplete backend accepted");
}

void TestCommitsCompletePreparedStack() {
    FakeContext context;
    const auto outcome = terrain::ExecuteTransaction(AppendPlan(2U), Backend(context));
    Expect(outcome.result == terrain::TransactionResult::committed,
        "complete transaction did not commit");
    Expect(outcome.prepared_count == 2U && outcome.published_count == 2U,
        "commit counts changed");
    Expect(context.prepare_calls == 2U && context.begin_calls == 1U &&
            context.append_calls == 2U && context.commit_calls == 2U,
        "commit callback sequence incomplete");
    Expect(context.release_calls == 0U && context.rollback_calls == 0U &&
            context.quarantine_calls == 0U,
        "successful transaction used failure cleanup");
    Expect(context.color_count == 5U && context.mask_count == 5U,
        "paired target counts not published");
}

void TestPrepareFailureTouchesNoTarget() {
    FakeContext context;
    context.fail_prepare_at = 1U;
    const auto outcome = terrain::ExecuteTransaction(AppendPlan(3U), Backend(context));
    Expect(outcome.result == terrain::TransactionResult::prepare_failed,
        "prepare failure result changed");
    Expect(outcome.prepared_count == 1U && outcome.published_count == 0U,
        "prepare failure counts changed");
    Expect(context.prepare_calls == 2U && context.release_calls == 2U,
        "partial preparation was not fully released");
    Expect(context.begin_calls == 0U && context.append_calls == 0U,
        "prepare failure touched publication target");
    Expect(context.color_count == 3U && context.mask_count == 3U,
        "prepare failure changed paired counts");
}

void TestRejectsInvalidOrSharedOwnershipProofs() {
    constexpr std::array cases{
        BadProof::shared_image,
        BadProof::shared_pixels,
        BadProof::source_image_alias,
        BadProof::source_pixels_alias,
        BadProof::immutable_image,
        BadProof::zero_bytes,
    };

    for (const auto proof : cases) {
        FakeContext context;
        context.bad_proof_at = proof == BadProof::shared_image ||
                                       proof == BadProof::shared_pixels
                                   ? 1U
                                   : 0U;
        context.bad_proof = proof;
        const auto layer_count = context.bad_proof_at + 1U;
        const auto outcome = terrain::ExecuteTransaction(
            AppendPlan(layer_count), Backend(context));
        Expect(outcome.result == terrain::TransactionResult::ownership_rejected,
            "unsafe ownership proof accepted");
        Expect(context.release_calls == layer_count,
            "unsafe ownership resources not released");
        Expect(context.begin_calls == 0U,
            "unsafe ownership reached publication target");
    }
}

void TestReserveFailureReleasesEverything() {
    FakeContext context;
    context.fail_begin = true;
    const auto outcome = terrain::ExecuteTransaction(AppendPlan(2U), Backend(context));
    Expect(outcome.result == terrain::TransactionResult::publication_reserve_failed,
        "reserve failure result changed");
    Expect(context.release_calls == 2U && context.append_calls == 0U,
        "reserve failure cleanup changed");
    Expect(context.color_count == 3U && context.mask_count == 3U,
        "reserve failure changed target counts");
}

void TestAppendFailureRollsBackAndReleases() {
    FakeContext context;
    context.fail_append_at = 1U;
    const auto outcome = terrain::ExecuteTransaction(AppendPlan(3U), Backend(context));
    Expect(outcome.result == terrain::TransactionResult::publication_append_failed,
        "append failure result changed");
    Expect(outcome.published_count == 1U, "completed append count changed");
    Expect(context.rollback_calls == 1U && context.release_calls == 3U,
        "append failure did not rollback and release");
    Expect(context.commit_calls == 0U && context.quarantine_calls == 0U,
        "append failure transferred ownership");
    Expect(context.color_count == 3U && context.mask_count == 3U,
        "rollback did not restore paired vector counts");
}

void TestRollbackFailureQuarantinesInsteadOfFreeing() {
    FakeContext context;
    context.fail_append_at = 1U;
    context.fail_rollback = true;
    const auto outcome = terrain::ExecuteTransaction(AppendPlan(3U), Backend(context));
    Expect(outcome.result == terrain::TransactionResult::rollback_failed,
        "rollback failure result changed");
    Expect(context.release_calls == 0U,
        "rollback failure freed possibly published resources");
    Expect(context.quarantine_calls == 3U,
        "rollback failure did not quarantine every prepared layer");
    Expect(context.commit_calls == 0U,
        "rollback failure reported ordinary ownership transfer");
}

}  // namespace

int main() {
    TestUnchangedRequiresNoBackend();
    TestRejectsInvalidPlanAndBackend();
    TestCommitsCompletePreparedStack();
    TestPrepareFailureTouchesNoTarget();
    TestRejectsInvalidOrSharedOwnershipProofs();
    TestReserveFailureReleasesEverything();
    TestAppendFailureRollsBackAndReleases();
    TestRollbackFailureQuarantinesInsteadOfFreeing();
    std::cout << "terrain material transaction tests passed\n";
    return EXIT_SUCCESS;
}
