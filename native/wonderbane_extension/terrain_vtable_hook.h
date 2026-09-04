#pragma once

#include <cstdint>

namespace wonderbane::extension::terrain_material {

enum class VtableHookResult : std::uint8_t {
    ok,
    unsupported_platform,
    invalid_argument,
    already_installed,
    unexpected_original,
    protection_failed,
    exchange_failed,
    restore_conflict,
};

struct VtableHook {
    void** slot = nullptr;
    void* expected_original = nullptr;
    void* replacement = nullptr;
    bool installed = false;
};

// Installation is compare-and-swap based and succeeds only while the slot still
// contains the exact reviewed target. Removal likewise restores only our own
// replacement, so another hook is never silently overwritten.
[[nodiscard]] VtableHookResult InstallVtableHook(
    VtableHook& hook,
    void** slot,
    void* expected_original,
    void* replacement) noexcept;

[[nodiscard]] VtableHookResult RemoveVtableHook(
    VtableHook& hook) noexcept;

}  // namespace wonderbane::extension::terrain_material
