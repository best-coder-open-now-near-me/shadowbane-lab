#pragma once
#include "event_channel.h"
#include "graphics_status.h"
namespace wonderbane::extension {
DWORD StartEffects(const ProcessIdentity&) noexcept;
void StopEffects() noexcept;
// Null camera invalidates history. Only call at the reviewed world/UI boundary.
// Only the shared scene authority may establish safe transparency composition.
// Unknown is unsafe; suppression lasts until an acknowledged disable/re-enable.
void DrawEffects(const GraphicsCameraState*, bool transparency_safe=false) noexcept;
}
