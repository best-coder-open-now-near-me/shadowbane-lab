#pragma once
#include "graphics_status.h"
namespace wonderbane::extension {
using SceneDraw = void(*)(void*) noexcept;
// Reviewed scene/UI boundary only. Preserves driver state; callback may draw
// immediate geometry, but must not modify programs, FBOs or matrix stack depth.
bool RenderSceneGeometry(const GraphicsCameraState*, SceneDraw, void*) noexcept;
}
