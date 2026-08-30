#pragma once

#include "event_channel.h"

#include <Windows.h>

namespace wonderbane::extension {

constexpr bool IsWorldMapActionTestInput(
    const DWORD flags,
    const ULONG_PTR extra_info
) noexcept {
    return (
        (flags & LLMHF_INJECTED) != 0U
        && (flags & LLMHF_LOWER_IL_INJECTED) == 0U
        && extra_info == kWorldMapActionTestInputTag
    );
}

constexpr bool IsAcceptedWorldMapPointerInput(
    const DWORD flags,
    const ULONG_PTR extra_info
) noexcept {
    const bool injected = (flags & LLMHF_INJECTED) != 0U;
    const bool lower_integrity_injected = (
        flags & LLMHF_LOWER_IL_INJECTED
    ) != 0U;
    return (
        (!injected && !lower_integrity_injected)
        || IsWorldMapActionTestInput(flags, extra_info)
    );
}

bool IsReviewedWorldMapClient() noexcept;
DWORD StartWorldMapCapture(
    HMODULE extension_module,
    const ProcessIdentity& identity
) noexcept;
void StopWorldMapCapture() noexcept;

}  // namespace wonderbane::extension
