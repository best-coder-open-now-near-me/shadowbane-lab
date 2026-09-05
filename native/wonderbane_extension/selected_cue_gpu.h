#pragma once
#include "selected_cue.h"
namespace wonderbane::extension::cue {
// All calls run on the owning GL context, inside the verified main scene.
bool BeginMask() noexcept;
bool BeforeOwnedDraw() noexcept;
bool AfterOwnedDraw() noexcept;
bool CompositeMask(const Settings&, const Direction&) noexcept;
void DiscardMask() noexcept;
void ReleaseMask() noexcept;
const char* MaskFragmentSource() noexcept;
const char* GlowFragmentSource() noexcept;
}
