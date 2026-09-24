#pragma once
#include "vendor_menu_wire.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::vendor_menu {
using Admission = bool (*)(void*) noexcept;
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept;
wire::Outcome Invoke(std::uintptr_t, const movement::NativeScene&, wire::Verb,
    const wire::Command&, Admission, void*) noexcept;
}
