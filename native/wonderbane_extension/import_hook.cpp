#include "import_hook.h"

namespace wonderbane::extension {

DWORD ReplaceImportAddressSlot(
    std::uint32_t* const slot,
    const std::uint32_t expected,
    const std::uint32_t replacement
) noexcept {
    if (slot == nullptr) {
        return ERROR_INVALID_PARAMETER;
    }
    DWORD previous_protection = 0U;
    if (VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE, &previous_protection) == FALSE) {
        return GetLastError();
    }
    const LONG previous = InterlockedCompareExchange(
        reinterpret_cast<volatile LONG*>(slot),
        static_cast<LONG>(replacement),
        static_cast<LONG>(expected)
    );
    DWORD ignored_protection = 0U;
    const BOOL restore_result = VirtualProtect(
        slot,
        sizeof(*slot),
        previous_protection,
        &ignored_protection
    );
    if (previous != static_cast<LONG>(expected)) {
        return ERROR_INVALID_DATA;
    }
    if (restore_result == FALSE) {
        const DWORD restore_error = GetLastError();
        InterlockedCompareExchange(
            reinterpret_cast<volatile LONG*>(slot),
            static_cast<LONG>(expected),
            static_cast<LONG>(replacement)
        );
        VirtualProtect(slot, sizeof(*slot), previous_protection, &ignored_protection);
        return restore_error;
    }
    return ERROR_SUCCESS;
}

}  // namespace wonderbane::extension
