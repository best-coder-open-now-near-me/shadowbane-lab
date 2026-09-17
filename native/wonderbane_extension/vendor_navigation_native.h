#pragma once
#include "vendor_navigation_wire.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::vendor_navigation {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept;
bool FindVendorControl(std::uintptr_t, const wire::Snapshot&, wire::Key, std::uint32_t&) noexcept;
bool FindGuardControl(std::uintptr_t, const wire::Snapshot&, wire::Key, std::uint32_t&) noexcept;
bool InvokeGuard(std::uintptr_t, const wire::Snapshot&, wire::Key) noexcept;
bool InvokeVendor(std::uintptr_t, const wire::Snapshot&, wire::Key) noexcept;
}
