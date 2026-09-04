#pragma once

#include "terrain_material_plan.h"

#include <cstdint>
#include <span>

namespace wonderbane::extension::terrain_material {

// Builder-scoped state. The original builder remains authoritative for terrain
// geometry and ownership; only its material-append region argument may be
// substituted after exact registered coverage is proven.
void BeginTerrainBuild(Token terrain_key) noexcept;
void AbortTerrainBuild() noexcept;

// Called by the generated append bridge before invoking the stock routine.
// this_pointer and arguments are mutable solely so one validated region slot can
// be replaced. All other raw values are preserved bit-for-bit.
void RewriteMaterialAppendInvocation(
    void*& this_pointer,
    std::span<std::uint32_t> arguments) noexcept;

}  // namespace wonderbane::extension::terrain_material
