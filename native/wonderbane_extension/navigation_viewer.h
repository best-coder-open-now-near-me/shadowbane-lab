#pragma once
#include "graphics_status.h"
#include "navigation_protocol.h"

namespace wonderbane::extension {
// Called only at the reviewed scene/UI boundary, before any UI drawing.
void DrawNavigationInspector() noexcept;
// Draw validated, bounded diagnostics using core OpenGL. The caller owns its
// current context; this restores every touched state and never writes depth.
bool RenderNavigationGeometry(const navigation::FrameHeader& frame,
                              const navigation::Line* lines,
                              const GraphicsCameraState* camera,
                              bool live_placement = true) noexcept;
}  // namespace wonderbane::extension
