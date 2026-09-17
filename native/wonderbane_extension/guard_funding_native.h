#pragma once
#include "guard_funding_wire.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::guard_funding {
// Owner-thread only. The purse getter borrows the current lifetime and is read-only.
bool Capture(std::uintptr_t, const movement::NativeScene&, std::uint32_t direction,
    wire::Snapshot&, bool& top) noexcept;
using Admission = bool (*)(void*) noexcept;
// Set through the ordinary amount setter, recapture all inputs, re-admit, then
// activate the exact owned ACCEPT action. False after entry is uncertain.
bool Invoke(std::uintptr_t, const movement::NativeScene&, const wire::Command&,
    Admission, void*) noexcept;
}
