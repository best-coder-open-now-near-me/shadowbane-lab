#pragma once
#include "graphics_status.h"
#include <cstddef>
#include <cstdint>
namespace wonderbane::extension {
DWORD StartSelectedCue(std::uint8_t*,std::size_t,const char*) noexcept;
void StopSelectedCue() noexcept;
void BeginSelectedCueScene(const GraphicsCameraState*) noexcept;
void FinishSelectedCueScene(const GraphicsCameraState*) noexcept;
void EndSelectedCueFrame() noexcept;
void DiscardSelectedCueScene() noexcept;
// Called by the lifecycle owner before deleting the owning context.
void ReleaseSelectedCueContext() noexcept;
}
