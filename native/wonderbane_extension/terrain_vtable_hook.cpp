#include "terrain_vtable_hook.h"

#if defined(_WIN32)
#include <windows.h>
#endif

namespace wonderbane::extension::terrain_material {

VtableHookResult InstallVtableHook(
    VtableHook& hook,
    void** slot,
    void* expected_original,
    void* replacement) noexcept {
#if !defined(_WIN32)
    (void)hook;
    (void)slot;
    (void)expected_original;
    (void)replacement;
    return VtableHookResult::unsupported_platform;
#else
    if (hook.installed) {
        return VtableHookResult::already_installed;
    }
    if (slot == nullptr || expected_original == nullptr || replacement == nullptr ||
        expected_original == replacement) {
        return VtableHookResult::invalid_argument;
    }

    DWORD old_protection = 0U;
    if (!VirtualProtect(
            slot,
            sizeof(*slot),
            PAGE_READWRITE,
            &old_protection)) {
        return VtableHookResult::protection_failed;
    }

    auto* atomic_slot = reinterpret_cast<void* volatile*>(slot);
    void* previous = InterlockedCompareExchangePointer(
        atomic_slot,
        replacement,
        expected_original);
    if (previous != expected_original) {
        DWORD ignored = 0U;
        VirtualProtect(slot, sizeof(*slot), old_protection, &ignored);
        return VtableHookResult::unexpected_original;
    }

    DWORD ignored = 0U;
    if (!VirtualProtect(slot, sizeof(*slot), old_protection, &ignored)) {
        // The page is still writable. Undo our exchange before reporting the
        // failed installation so the caller never receives a hidden active hook.
        previous = InterlockedCompareExchangePointer(
            atomic_slot,
            expected_original,
            replacement);
        DWORD second_ignored = 0U;
        VirtualProtect(slot, sizeof(*slot), old_protection, &second_ignored);
        if (previous != replacement) {
            return VtableHookResult::exchange_failed;
        }
        return VtableHookResult::protection_failed;
    }

    hook.slot = slot;
    hook.expected_original = expected_original;
    hook.replacement = replacement;
    hook.installed = true;
    return VtableHookResult::ok;
#endif
}

VtableHookResult RemoveVtableHook(VtableHook& hook) noexcept {
#if !defined(_WIN32)
    (void)hook;
    return VtableHookResult::unsupported_platform;
#else
    if (!hook.installed || hook.slot == nullptr ||
        hook.expected_original == nullptr || hook.replacement == nullptr) {
        return VtableHookResult::invalid_argument;
    }

    DWORD old_protection = 0U;
    if (!VirtualProtect(
            hook.slot,
            sizeof(*hook.slot),
            PAGE_READWRITE,
            &old_protection)) {
        return VtableHookResult::protection_failed;
    }

    auto* atomic_slot = reinterpret_cast<void* volatile*>(hook.slot);
    void* previous = InterlockedCompareExchangePointer(
        atomic_slot,
        hook.expected_original,
        hook.replacement);

    DWORD ignored = 0U;
    const bool protection_restored = VirtualProtect(
        hook.slot,
        sizeof(*hook.slot),
        old_protection,
        &ignored) != FALSE;

    if (previous != hook.replacement) {
        // Another owner replaced our hook. Do not overwrite it with the stale
        // original and do not claim that we still own the slot.
        hook.installed = false;
        return VtableHookResult::restore_conflict;
    }

    hook = {};
    return protection_restored
        ? VtableHookResult::ok
        : VtableHookResult::protection_failed;
#endif
}

}  // namespace wonderbane::extension::terrain_material
