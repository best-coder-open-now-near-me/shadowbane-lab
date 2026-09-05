#pragma once
#include "graphics_status.h"
namespace wonderbane::extension {
using SceneDraw = void(*)(void*) noexcept;
// Verified background or scene/UI boundary only; caller owns stage authority.
// Preserves driver state; callback may draw
// immediate geometry. It must restore any program/FBO changes before returning
// and balance matrix stack operations. Such non-attrib state is caller-owned.
bool RenderSceneGeometry(const GraphicsCameraState*, SceneDraw, void*) noexcept;
}
