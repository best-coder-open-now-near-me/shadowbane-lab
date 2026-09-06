#pragma once
#include <cstdint>
namespace wonderbane::extension::movement {
// Seal all loaded executable code against the exact reviewed image, normalizing
// only its authenticated PE relocations. Accept the original or exact reviewed
// bootstrap-v1 prepared file; compare loaded text with the actual prepared bytes.
// No game code is executed during verification.
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept;
}
