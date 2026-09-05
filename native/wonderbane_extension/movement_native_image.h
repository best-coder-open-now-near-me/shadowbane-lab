#pragma once
#include <cstdint>
namespace wonderbane::extension::movement {
// Seal all loaded executable code against the exact reviewed image, normalizing
// only its authenticated PE relocations. No native call is made here.
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept;
}
