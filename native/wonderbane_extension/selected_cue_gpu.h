#pragma once
#include "selected_cue.h"
namespace wonderbane::extension::cue {
// All calls run on the owning GL context, inside the verified main scene.
bool BeginMask() noexcept;
// Bracket each owned wrapper. Raw meshes share one frame depth target;
// request the delta baseline lazily before an immediate/display-list draw.
bool BeforeOwnedDraw() noexcept;
bool BeforeLegacyGeometry() noexcept;
using GeometryDraw = void(*)(void*) noexcept;
bool CaptureGeometry(GeometryDraw, void*) noexcept;
bool AfterOwnedDraw() noexcept;
bool CompositeMask(const Settings&, const Direction&) noexcept;
void DiscardMask() noexcept;
void ReleaseMask() noexcept;
std::uint64_t AllocatedMaskBytes() noexcept;
const char* MaskFragmentSource() noexcept;
const char* GlowFragmentSource() noexcept;
}
