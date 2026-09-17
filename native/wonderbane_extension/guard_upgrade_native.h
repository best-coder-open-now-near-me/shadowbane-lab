#pragma once
#include "guard_upgrade_wire.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::guard_upgrade {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&, bool& top) noexcept;
// Caller must hold the owning-thread lifetime/foreground/producer lease and
// compare a fresh snapshot immediately before this ordinary confirmation action.
bool Invoke(std::uintptr_t, const wire::Snapshot&) noexcept;
}
