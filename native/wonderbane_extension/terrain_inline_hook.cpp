#include "terrain_inline_hook.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

#if defined(_WIN32) && !defined(_WIN64)
#include <windows.h>
#endif

namespace wonderbane::extension::terrain_material {
namespace {

#if defined(_WIN32) && !defined(_WIN64)

[[nodiscard]] bool ReadableExecutableRange(
    const void* address,
    const std::size_t size) noexcept {
    if (address == nullptr || size == 0U) {
        return false;
    }
    const auto begin = reinterpret_cast<std::uintptr_t>(address);
    const auto end = begin + size;
    if (end < begin) {
        return false;
    }

    auto cursor = begin;
    while (cursor < end) {
        MEMORY_BASIC_INFORMATION information{};
        if (VirtualQuery(
                reinterpret_cast<const void*>(cursor),
                &information,
                sizeof(information)) != sizeof(information)) {
            return false;
        }
        if (information.State != MEM_COMMIT ||
            (information.Protect & PAGE_GUARD) != 0U ||
            (information.Protect & PAGE_NOACCESS) != 0U) {
            return false;
        }
        const DWORD executable = information.Protect & 0xFFU;
        if (executable != PAGE_EXECUTE &&
            executable != PAGE_EXECUTE_READ &&
            executable != PAGE_EXECUTE_READWRITE &&
            executable != PAGE_EXECUTE_WRITECOPY) {
            return false;
        }
        const auto region_begin = reinterpret_cast<std::uintptr_t>(
            information.BaseAddress);
        const auto region_end = region_begin + information.RegionSize;
        if (region_end <= cursor) {
            return false;
        }
        cursor = region_end;
    }
    return true;
}

[[nodiscard]] bool EncodeRelativeJump(
    std::uint8_t* destination,
    const void* instruction,
    const void* target) noexcept {
    if (destination == nullptr || instruction == nullptr || target == nullptr) {
        return false;
    }
    const auto source = reinterpret_cast<std::intptr_t>(instruction);
    const auto target_address = reinterpret_cast<std::intptr_t>(target);
    const auto displacement = target_address - (source + 5);
    if (displacement < std::numeric_limits<std::int32_t>::min() ||
        displacement > std::numeric_limits<std::int32_t>::max()) {
        return false;
    }
    destination[0] = 0xE9U;
    const auto relative = static_cast<std::int32_t>(displacement);
    std::memcpy(destination + 1U, &relative, sizeof(relative));
    return true;
}

void QuarantineTrampoline(InlineHook& hook) noexcept {
    hook.installed = false;
    hook.trampoline_quarantined = hook.trampoline != nullptr;
}

#endif

}  // namespace

InlineHookResult InstallInlineHook(
    InlineHook& hook,
    void* target,
    void* replacement,
    const std::span<const std::uint8_t> expected_prologue) noexcept {
#if !defined(_WIN32) || defined(_WIN64)
    (void)hook;
    (void)target;
    (void)replacement;
    (void)expected_prologue;
    return InlineHookResult::unsupported_platform;
#else
    if (hook.installed) {
        return InlineHookResult::already_installed;
    }
    if (hook.trampoline_quarantined || target == nullptr ||
        replacement == nullptr || target == replacement ||
        expected_prologue.size() < 5U ||
        expected_prologue.size() > kMaximumInlinePatch) {
        return InlineHookResult::invalid_argument;
    }
    if (!ReadableExecutableRange(target, expected_prologue.size())) {
        return InlineHookResult::target_unreadable;
    }
    if (std::memcmp(
            target,
            expected_prologue.data(),
            expected_prologue.size()) != 0) {
        return InlineHookResult::prologue_mismatch;
    }

    const auto trampoline_size = expected_prologue.size() + 5U;
    auto* trampoline = static_cast<std::uint8_t*>(VirtualAlloc(
        nullptr,
        trampoline_size,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_READWRITE));
    if (trampoline == nullptr) {
        return InlineHookResult::trampoline_allocation_failed;
    }
    std::memcpy(
        trampoline,
        expected_prologue.data(),
        expected_prologue.size());
    if (!EncodeRelativeJump(
            trampoline + expected_prologue.size(),
            trampoline + expected_prologue.size(),
            static_cast<std::uint8_t*>(target) + expected_prologue.size())) {
        VirtualFree(trampoline, 0U, MEM_RELEASE);
        return InlineHookResult::displacement_out_of_range;
    }

    DWORD trampoline_protection = 0U;
    if (!VirtualProtect(
            trampoline,
            trampoline_size,
            PAGE_EXECUTE_READ,
            &trampoline_protection)) {
        VirtualFree(trampoline, 0U, MEM_RELEASE);
        return InlineHookResult::protection_failed;
    }
    FlushInstructionCache(GetCurrentProcess(), trampoline, trampoline_size);

    std::array<std::uint8_t, kMaximumInlinePatch> patch{};
    std::fill_n(patch.begin(), expected_prologue.size(), 0x90U);
    if (!EncodeRelativeJump(patch.data(), target, replacement)) {
        VirtualFree(trampoline, 0U, MEM_RELEASE);
        return InlineHookResult::displacement_out_of_range;
    }

    DWORD old_protection = 0U;
    if (!VirtualProtect(
            target,
            expected_prologue.size(),
            PAGE_EXECUTE_READWRITE,
            &old_protection)) {
        VirtualFree(trampoline, 0U, MEM_RELEASE);
        return InlineHookResult::protection_failed;
    }

    InlineHookResult result = InlineHookResult::ok;
    if (std::memcmp(
            target,
            expected_prologue.data(),
            expected_prologue.size()) != 0) {
        result = InlineHookResult::patch_conflict;
    } else {
        std::memcpy(target, patch.data(), expected_prologue.size());
        FlushInstructionCache(
            GetCurrentProcess(), target, expected_prologue.size());
    }

    DWORD ignored = 0U;
    const bool restored = VirtualProtect(
        target,
        expected_prologue.size(),
        old_protection,
        &ignored) != FALSE;

    if (result != InlineHookResult::ok) {
        VirtualFree(trampoline, 0U, MEM_RELEASE);
        return result;
    }
    if (!restored) {
        // Restore the target while the page is still writable. Do not return a
        // hidden live hook after a failed protection transition.
        std::memcpy(
            target,
            expected_prologue.data(),
            expected_prologue.size());
        FlushInstructionCache(
            GetCurrentProcess(), target, expected_prologue.size());
        DWORD second_ignored = 0U;
        VirtualProtect(
            target,
            expected_prologue.size(),
            old_protection,
            &second_ignored);
        VirtualFree(trampoline, 0U, MEM_RELEASE);
        return InlineHookResult::protection_failed;
    }

    hook.target = target;
    hook.replacement = replacement;
    hook.trampoline = trampoline;
    std::copy(
        expected_prologue.begin(),
        expected_prologue.end(),
        hook.original.begin());
    std::copy_n(
        patch.begin(), expected_prologue.size(), hook.installed_patch.begin());
    hook.patch_length = expected_prologue.size();
    hook.installed = true;
    hook.trampoline_quarantined = false;
    return InlineHookResult::ok;
#endif
}

InlineHookResult RemoveInlineHook(InlineHook& hook) noexcept {
#if !defined(_WIN32) || defined(_WIN64)
    (void)hook;
    return InlineHookResult::unsupported_platform;
#else
    if (!hook.installed || hook.target == nullptr || hook.trampoline == nullptr ||
        hook.patch_length < 5U || hook.patch_length > kMaximumInlinePatch) {
        return InlineHookResult::invalid_argument;
    }

    DWORD old_protection = 0U;
    if (!VirtualProtect(
            hook.target,
            hook.patch_length,
            PAGE_EXECUTE_READWRITE,
            &old_protection)) {
        return InlineHookResult::protection_failed;
    }

    if (std::memcmp(
            hook.target,
            hook.installed_patch.data(),
            hook.patch_length) != 0) {
        DWORD ignored = 0U;
        VirtualProtect(
            hook.target,
            hook.patch_length,
            old_protection,
            &ignored);
        QuarantineTrampoline(hook);
        return InlineHookResult::restore_conflict;
    }

    std::memcpy(
        hook.target,
        hook.original.data(),
        hook.patch_length);
    FlushInstructionCache(
        GetCurrentProcess(), hook.target, hook.patch_length);

    DWORD ignored = 0U;
    const bool restored = VirtualProtect(
        hook.target,
        hook.patch_length,
        old_protection,
        &ignored) != FALSE;
    if (!restored) {
        // The original code is back, but the page protection could not be
        // proven. Keep the trampoline allocated because callers may still hold
        // it while shutdown proceeds.
        QuarantineTrampoline(hook);
        return InlineHookResult::protection_failed;
    }

    VirtualFree(hook.trampoline, 0U, MEM_RELEASE);
    hook = {};
    return InlineHookResult::ok;
#endif
}

}  // namespace wonderbane::extension::terrain_material
