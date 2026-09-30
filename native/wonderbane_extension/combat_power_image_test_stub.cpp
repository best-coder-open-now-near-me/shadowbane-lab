#include "combat_power_observer.h"
// Standalone image-verifier fixtures never install native power hooks.
namespace wonderbane::extension::combat::power {
bool NormalizeOwnedCode(std::uintptr_t, std::uint32_t, std::span<std::uint8_t>,
    std::span<const std::uint8_t>) noexcept { return true; }
}
