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
// Native-order RGB enhancement. Always submits the supplied original once.
// 0 applied; 3 program; 4 no free texture stage; 5 unsafe state; 6 resource/context.
int DrawMaterial(const Settings&, GeometryDraw, void*) noexcept;
std::uint64_t AllocatedMaterialBytes() noexcept;
bool AfterOwnedDraw() noexcept;
bool CompositeMask(const Settings&, const Direction&) noexcept;
void DiscardMask() noexcept;
void ReleaseMask() noexcept;
std::uint64_t AllocatedMaskBytes() noexcept;
const char* MaskFragmentSource() noexcept;
const char* GlowFragmentSource() noexcept;
}
