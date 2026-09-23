#pragma once

#include <Windows.h>

namespace wonderbane::extension {

DWORD StartPassiveCameraObservation() noexcept;
void StopPassiveCameraObservation() noexcept;

}  // namespace wonderbane::extension
