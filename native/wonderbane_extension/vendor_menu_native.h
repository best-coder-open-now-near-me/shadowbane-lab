#pragma once
#include "vendor_menu_wire.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::vendor_menu {
using Admission = bool (*)(void*) noexcept;
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept;
wire::Outcome Invoke(std::uintptr_t, const movement::NativeScene&, wire::Verb,
    const wire::Command&, Admission, void*) noexcept;
// Generalized creation preserves the native CREATE caller's checks. The runtime
// admission callback additionally verifies ownership of active quantity orders.
vendor::wire::Outcome InvokeRandomCreate(std::uintptr_t, const movement::NativeScene&,
    const vendor::wire::Snapshot&, Admission, void*, bool orders = false) noexcept;
}
