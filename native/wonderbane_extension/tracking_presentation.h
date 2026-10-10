#pragma once
#include "movement_lifetime.h"
#include <array>
namespace wonderbane::extension::tracking::presentation {
using Owner = std::array<std::uint8_t, 16>;
// Native presentation policy only: never query/response or gameplay authority.
bool Bind(std::uintptr_t image) noexcept;
void Unbind() noexcept;
void Arm(const movement::NativeScene&, const Owner&) noexcept;
void Maintain(const movement::NativeScene&, const Owner&) noexcept;
void Retire(const Owner&) noexcept;
void ManualQuery() noexcept;
struct Processing { std::uint64_t policy = 0; bool entered = false; };
Processing Begin(const movement::NativeScene&) noexcept;
void End(const movement::NativeScene&, Processing, bool complete_hunt_foe, bool native_returned = true) noexcept;
}
