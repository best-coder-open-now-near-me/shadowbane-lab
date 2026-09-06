#pragma once
#include "graphics_status.h"
namespace wonderbane::extension {
using SceneDraw = void(*)(void*) noexcept;
// Authority for late scene compositing, separate from camera validity and GL state.
// No supported late path currently establishes complete native foreground coverage.
// Native-order material enhancement does not use this late-composite authority.
bool IsWorldEnhancementCompositionSafe() noexcept;
// Verified background or scene/UI boundary only; caller owns stage authority.
// Preserves driver state; callback may draw immediate geometry. The guard saves
// and restores the current program and core/ARB program-pipeline binding,
// temporarily disabling both. The callback must not mutate native program or
// pipeline objects, must restore FBO changes, and balance matrix stack operations.
// Legal outside glBegin/glEnd and display-list compilation. Read-only: reject
// active or unknown native sample/stream-zero primitive queries; do not pause or replace query objects.
bool AreSceneGeometryQueriesInactive() noexcept;
bool RenderSceneGeometry(const GraphicsCameraState*, SceneDraw, void*) noexcept;
}
