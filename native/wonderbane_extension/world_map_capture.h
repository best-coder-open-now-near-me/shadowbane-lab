#pragma once

#include "event_channel.h"

#include <Windows.h>

namespace wonderbane::extension {

bool IsReviewedWorldMapClient() noexcept;
DWORD StartWorldMapCapture(
    HMODULE extension_module,
    const ProcessIdentity& identity
) noexcept;
void StopWorldMapCapture() noexcept;

}  // namespace wonderbane::extension
