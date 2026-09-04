#pragma once

#include "terrain_material_plan.h"
#include "terrain_material_transaction.h"

#include <cstdint>

namespace wonderbane::extension::terrain_material {

enum class ClientRepairResult : std::uint8_t {
    unchanged,
    repaired,
    rejected,
    unavailable,
    failed,
};

// Called only from the reviewed builder hook after the original builder has
// returned an ArcTerrain. The adapter must finish before the caller can enter
// the terrain finalizer. It may change only the render-source material stack and
// extension-owned alpha resources; heights, geometry, zone ownership, and
// archive-backed images are outside its authority.
[[nodiscard]] ClientRepairResult RepairBuiltTerrain(
    void* arc_terrain,
    Token terrain_key) noexcept;

// Releases adapter-owned quarantine records at process shutdown only after the
// builder hook is gone. Published client references retain their own counts.
void ShutdownClientAdapter() noexcept;

}  // namespace wonderbane::extension::terrain_material
