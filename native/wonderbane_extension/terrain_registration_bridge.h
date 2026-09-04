#pragma once

#include <cstdint>
#include <span>

namespace wonderbane::extension::terrain_material {

void SetMaterialRegistrationTrampoline(void* trampoline) noexcept;
[[nodiscard]] void* MaterialRegistrationHookAddress() noexcept;

// Called after the reviewed registration routine has completed, so the region
// map at +0x64 is already populated. The adapter treats every raw slot as
// untrusted until one validates as a bounded region object.
void RecordMaterialRegistration(
    void* this_pointer,
    std::span<const std::uint32_t> arguments,
    std::uintptr_t result) noexcept;

}  // namespace wonderbane::extension::terrain_material
