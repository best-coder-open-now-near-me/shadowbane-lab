#pragma once
#include "graphics_status.h"
namespace wonderbane::extension {
using SceneDraw = void(*)(void*) noexcept;
// Reviewed scene/UI boundary only. Preserves driver state; callback may draw
// immediate geometry. The guard saves and restores the current program and
// core/ARB program-pipeline binding, temporarily disabling both. The callback
// must not mutate native program/pipeline objects, must restore FBO changes,
// and must balance matrix stack operations.
bool RenderSceneGeometry(const GraphicsCameraState*, SceneDraw, void*) noexcept;
}
