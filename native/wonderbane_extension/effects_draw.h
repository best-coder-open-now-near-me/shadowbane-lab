#pragma once
#include "effects.h"
#include "graphics_status.h"
namespace wonderbane::extension {
bool RenderEffectsGeometry(const effects::Config&, const effects::Geometry&, const GraphicsCameraState&) noexcept;
}
