#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace wonderbane::extension::terrain_material {

constexpr std::size_t kMaximumInlinePatch = 16U;

enum class InlineHookResult : std::uint8_t {
    ok,
    unsupported_platform,
    invalid_argument,
    already_installed,
    target_unreadable,
    prologue_mismatch,
    trampoline_allocation_failed,
    displacement_out_of_range,
    protection_failed,
    patch_conflict,
    restore_conflict,
};

struct InlineHook {
    void* target = nullptr;
    void* replacement = nullptr;
    void* trampoline = nullptr;
    std::array<std::uint8_t, kMaximumInlinePatch> original{};
    std::array<std::uint8_t, kMaximumInlinePatch> installed_patch{};
    std::size_t patch_length = 0U;
    bool installed = false;
    bool trampoline_quarantined = false;
};

// expected_prologue must contain complete, relocation-free x86 instructions and
// be at least five bytes. The caller obtains it from the exact reviewed binary.
[[nodiscard]] InlineHookResult InstallInlineHook(
    InlineHook& hook,
    void* target,
    void* replacement,
    std::span<const std::uint8_t> expected_prologue) noexcept;

// Restores only when the target still contains our exact jump/NOP patch. A
// conflict never overwrites another owner and quarantines the trampoline.
[[nodiscard]] InlineHookResult RemoveInlineHook(InlineHook& hook) noexcept;

}  // namespace wonderbane::extension::terrain_material
