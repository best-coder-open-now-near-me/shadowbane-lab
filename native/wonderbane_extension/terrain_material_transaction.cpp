#include "terrain_material_transaction.h"

#include <array>

namespace wonderbane::extension::terrain_material {
namespace {

[[nodiscard]] bool ValidBackend(const TransactionBackend& backend) noexcept {
    return backend.prepare_owned_layer != nullptr &&
           backend.release_prepared_layer != nullptr &&
           backend.begin_publication != nullptr &&
           backend.append_prepared_layer != nullptr &&
           backend.rollback_publication != nullptr &&
           backend.commit_prepared_layer != nullptr &&
           backend.quarantine_prepared_layer != nullptr;
}

[[nodiscard]] bool ValidOwnershipProof(
    const PreparedLayer& prepared) noexcept {
    return prepared.color_texture != 0U &&
           prepared.mask_texture != 0U &&
           prepared.source_image != 0U &&
           prepared.source_pixels != 0U &&
           prepared.owned_image != 0U &&
           prepared.owned_pixels != 0U &&
           prepared.pixel_bytes != 0U &&
           prepared.owned_image_mutable &&
           prepared.source_image != prepared.owned_image &&
           prepared.source_pixels != prepared.owned_pixels;
}

[[nodiscard]] bool UniqueOwnership(
    const std::array<PreparedLayer, kMaximumLayers>& prepared,
    const std::size_t count,
    const PreparedLayer& candidate) noexcept {
    for (std::size_t index = 0U; index < count; ++index) {
        if (prepared[index].mask_texture == candidate.mask_texture ||
            prepared[index].owned_image == candidate.owned_image ||
            prepared[index].owned_pixels == candidate.owned_pixels) {
            return false;
        }
    }
    return true;
}

void ReleasePrepared(
    const TransactionBackend& backend,
    std::array<PreparedLayer, kMaximumLayers>& prepared,
    std::size_t count) noexcept {
    while (count != 0U) {
        --count;
        backend.release_prepared_layer(
            backend.context, prepared[count]);
    }
}

void QuarantinePrepared(
    const TransactionBackend& backend,
    std::array<PreparedLayer, kMaximumLayers>& prepared,
    const std::size_t count) noexcept {
    for (std::size_t index = 0U; index < count; ++index) {
        backend.quarantine_prepared_layer(
            backend.context, prepared[index]);
    }
}

}  // namespace

TransactionOutcome ExecuteTransaction(
    const Plan& plan,
    const TransactionBackend& backend) noexcept {
    if (plan.decision == Decision::unchanged &&
        plan.layer_count == 0U && plan.region_count == 0U) {
        return {};
    }

    if (plan.decision != Decision::append ||
        plan.layer_count == 0U ||
        plan.layer_count > kMaximumLayers ||
        plan.region_count == 0U ||
        plan.region_count > kMaximumDepth) {
        return TransactionOutcome{TransactionResult::invalid_plan, 0U, 0U};
    }
    if (!ValidBackend(backend)) {
        return TransactionOutcome{TransactionResult::invalid_backend, 0U, 0U};
    }

    std::array<PreparedLayer, kMaximumLayers> prepared{};
    std::size_t prepared_count = 0U;

    for (std::size_t index = 0U; index < plan.layer_count; ++index) {
        auto& candidate = prepared[index];
        if (!backend.prepare_owned_layer(
                backend.context, plan.additions[index], candidate)) {
            // A failing callback may still have acquired a subset of its
            // resources, so release the current slot as well as prior slots.
            backend.release_prepared_layer(backend.context, candidate);
            ReleasePrepared(backend, prepared, prepared_count);
            return TransactionOutcome{
                TransactionResult::prepare_failed,
                prepared_count,
                0U};
        }

        if (!ValidOwnershipProof(candidate) ||
            !UniqueOwnership(prepared, prepared_count, candidate)) {
            ++prepared_count;
            ReleasePrepared(backend, prepared, prepared_count);
            return TransactionOutcome{
                TransactionResult::ownership_rejected,
                prepared_count,
                0U};
        }
        ++prepared_count;
    }

    PublicationCheckpoint checkpoint{};
    if (!backend.begin_publication(
            backend.context, plan.layer_count, checkpoint)) {
        ReleasePrepared(backend, prepared, prepared_count);
        return TransactionOutcome{
            TransactionResult::publication_reserve_failed,
            prepared_count,
            0U};
    }

    std::size_t published_count = 0U;
    for (std::size_t index = 0U; index < prepared_count; ++index) {
        if (!backend.append_prepared_layer(
                backend.context, prepared[index])) {
            if (!backend.rollback_publication(
                    backend.context, checkpoint)) {
                // The target may still retain any prepared handle, including a
                // partially appended current pair. Freeing here would risk a
                // use-after-free. Quarantine until process shutdown instead.
                QuarantinePrepared(backend, prepared, prepared_count);
                return TransactionOutcome{
                    TransactionResult::rollback_failed,
                    prepared_count,
                    published_count};
            }
            ReleasePrepared(backend, prepared, prepared_count);
            return TransactionOutcome{
                TransactionResult::publication_append_failed,
                prepared_count,
                published_count};
        }
        ++published_count;
    }

    for (std::size_t index = 0U; index < prepared_count; ++index) {
        backend.commit_prepared_layer(
            backend.context, prepared[index]);
    }
    return TransactionOutcome{
        TransactionResult::committed,
        prepared_count,
        published_count};
}

}  // namespace wonderbane::extension::terrain_material
