#pragma once

#include "terrain_client_verification.h"
#include "terrain_vtable_hook.h"

#include <cstdint>

namespace wonderbane::extension::terrain_material {

enum class RuntimeState : std::uint8_t {
    inactive,
    profile_disabled,
    verification_failed,
    hook_install_failed,
    active,
    shutdown_conflict,
};

struct RuntimeStatus {
    RuntimeState state = RuntimeState::inactive;
    ClientVerificationError verification =
        ClientVerificationError::unsupported_platform;
    VtableHookResult hook = VtableHookResult::invalid_argument;
    std::uint64_t builder_calls = 0U;
    std::uint64_t repaired_terrains = 0U;
    std::uint64_t rejected_terrains = 0U;
    std::uint64_t failed_terrains = 0U;
};

// These entry points are linked and called only by the full renderer profile.
// The diagnostics-only extension does not compile or invoke this runtime.
[[nodiscard]] bool InitializeTerrainMaterialRepair() noexcept;
void ShutdownTerrainMaterialRepair() noexcept;
[[nodiscard]] RuntimeStatus ReadTerrainMaterialRuntimeStatus() noexcept;

}  // namespace wonderbane::extension::terrain_material
