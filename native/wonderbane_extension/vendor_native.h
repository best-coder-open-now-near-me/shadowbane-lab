#pragma once
#include "vendor_wire.h"
#include "movement_lifetime.h"
#include <Windows.h>
namespace wonderbane::extension::vendor {
bool Capture(std::uintptr_t base, const movement::NativeScene&, wire::Snapshot&,
    std::uint32_t find_inventory_item, bool& inventory_contains, bool& top_menu) noexcept;
bool InvokeNative(std::uintptr_t base, wire::Verb, const wire::Snapshot&, std::uint32_t item) noexcept;
}
