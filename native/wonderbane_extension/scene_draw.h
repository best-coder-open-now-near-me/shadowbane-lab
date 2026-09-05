#pragma once
#include "graphics_status.h"
namespace wonderbane::extension {
using SceneDraw = void(*)(void*) noexcept;
// Verified background or scene/UI boundary only; caller owns stage authority.
// Preserves driver state; callback may draw immediate geometry. The guard saves
// and restores the current program and core/ARB program-pipeline binding,
// temporarily disabling both. The callback must not mutate native program or
// pipeline objects, must restore FBO changes, and balance matrix stack operations.
bool RenderSceneGeometry(const GraphicsCameraState*, SceneDraw, void*) noexcept;
}
