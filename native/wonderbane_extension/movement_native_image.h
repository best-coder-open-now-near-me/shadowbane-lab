#pragma once
#include <cstdint>
namespace wonderbane::extension::movement {
struct NativeMovementImageLayout {
    std::uint32_t image_size = 0;
    std::uint16_t section_count = 0;
};
// Seal all loaded executable code against the exact reviewed image, normalizing
// only its authenticated PE relocations. Accept the original or exact reviewed
// bootstrap-v1 prepared file; compare loaded text with the actual prepared bytes.
// No game code is executed during verification.
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept;
// Returns only layout read from the authenticated file and matched to the
// loaded PE header. Consumers must use this bound instead of an older constant.
bool VerifyNativeMovementImageLayout(
    std::uintptr_t& base, NativeMovementImageLayout& layout) noexcept;
}
