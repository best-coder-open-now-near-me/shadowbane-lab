#pragma once
#include "graphics_status.h"
#include <Windows.h>
#include <cstdint>
namespace wonderbane::extension {
DWORD StartSky(std::uint8_t*,std::size_t,const char*) noexcept;
void StopSky() noexcept;
void ObserveSkyCameraUpload(std::uintptr_t caller,bool legal) noexcept;
void BeginSkyBackground(const GraphicsCameraState*,bool scene) noexcept;
void DiscardSkyScene() noexcept;
void EndSkyFrame() noexcept;
}
