#pragma once
#include "city_window_wire.h"
#include "movement_lifetime.h"
namespace wonderbane::extension::city_window {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept;
bool InvokeOpen(std::uintptr_t, const wire::Snapshot&) noexcept;
}
