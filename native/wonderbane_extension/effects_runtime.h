#pragma once
#include "event_channel.h"
#include "graphics_status.h"
namespace wonderbane::extension {
DWORD StartEffects(const ProcessIdentity&) noexcept;
void StopEffects() noexcept;
// Null camera invalidates history. Only call at the reviewed world/UI boundary.
void DrawEffects(const GraphicsCameraState*) noexcept;
}
