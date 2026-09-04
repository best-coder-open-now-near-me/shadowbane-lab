#pragma once

#include "terrain_material_plan.h"

#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::terrain_material {

// Opaque handles are intentionally pointer-sized without exposing reverse-
// engineered client layouts to the transaction engine.
struct PreparedLayer {
    std::uintptr_t color_texture = 0U;
    std::uintptr_t mask_texture = 0U;
    std::uintptr_t source_image = 0U;
    std::uintptr_t source_pixels = 0U;
    std::uintptr_t owned_image = 0U;
    std::uintptr_t owned_pixels = 0U;
    std::size_t pixel_bytes = 0U;
    bool owned_image_mutable = false;
};

struct PublicationCheckpoint {
    std::uintptr_t opaque0 = 0U;
    std::uintptr_t opaque1 = 0U;
    std::size_t original_color_count = 0U;
    std::size_t original_mask_count = 0U;
};

// Every callback is noexcept by contract. prepare_owned_layer must produce a
// deep, tile-owned alpha image and texture. begin_publication must reserve all
// required storage before publishing an element. rollback_publication must
// restore both paired vectors to the checkpoint and drop every reference added
// since it. quarantine_layer keeps a prepared resource alive when rollback
// cannot prove restoration; it must never free the resource in that call.
struct TransactionBackend {
    void* context = nullptr;

    bool (*prepare_owned_layer)(
        void* context,
        const Layer& requested,
        PreparedLayer& prepared) noexcept = nullptr;

    void (*release_prepared_layer)(
        void* context,
        PreparedLayer& prepared) noexcept = nullptr;

    bool (*begin_publication)(
        void* context,
        std::size_t additional_layers,
        PublicationCheckpoint& checkpoint) noexcept = nullptr;

    bool (*append_prepared_layer)(
        void* context,
        const PreparedLayer& prepared) noexcept = nullptr;

    bool (*rollback_publication)(
        void* context,
        const PublicationCheckpoint& checkpoint) noexcept = nullptr;

    void (*commit_prepared_layer)(
        void* context,
        PreparedLayer& prepared) noexcept = nullptr;

    void (*quarantine_prepared_layer)(
        void* context,
        PreparedLayer& prepared) noexcept = nullptr;
};

enum class TransactionResult : std::uint8_t {
    unchanged,
    committed,
    invalid_plan,
    invalid_backend,
    prepare_failed,
    ownership_rejected,
    publication_reserve_failed,
    publication_append_failed,
    rollback_failed,
};

struct TransactionOutcome {
    TransactionResult result = TransactionResult::unchanged;
    std::size_t prepared_count = 0U;
    std::size_t published_count = 0U;
};

// Applies only Plan::append. No target is touched until every requested layer
// has passed deep-ownership validation. On ordinary failure, all prepared
// resources are released and both target vectors remain at their checkpoint.
[[nodiscard]] TransactionOutcome ExecuteTransaction(
    const Plan& plan,
    const TransactionBackend& backend) noexcept;

}  // namespace wonderbane::extension::terrain_material
