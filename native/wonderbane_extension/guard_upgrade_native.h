#pragma once
#include "guard_upgrade_response.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::guard_upgrade {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&, bool& top) noexcept;
// Read a complete, owned replacement roster and the exact requested guard.
bool CaptureReturn(std::uintptr_t, const movement::NativeScene&, const wire::Snapshot&,
    ReturnSnapshot&) noexcept;
// Caller must hold the owning-thread lifetime/foreground/producer lease and
// compare a fresh snapshot immediately before this ordinary confirmation action.
bool Invoke(std::uintptr_t, const wire::Snapshot&) noexcept;
}
