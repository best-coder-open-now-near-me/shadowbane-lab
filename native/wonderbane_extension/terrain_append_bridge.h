#pragma once

#include <cstdint>
#include <span>

namespace wonderbane::extension::terrain_material {

// Generated bridge entry points. The generated implementation uses the exact
// reviewed x86 stack cleanup from the client binary while exposing raw 32-bit
// slots to the adapter. No semantic role is assigned until the live call is
// correlated with the active builder, terrain key, and returned render source.
void SetMaterialAppendTrampoline(void* trampoline) noexcept;
[[nodiscard]] void* MaterialAppendHookAddress() noexcept;
[[nodiscard]] std::uintptr_t InvokeMaterialAppend(
    void* this_pointer,
    std::span<const std::uint32_t> arguments) noexcept;

// Implemented by the adapter and called synchronously by the generated bridge.
void RecordMaterialAppendEnter(
    void* this_pointer,
    std::span<const std::uint32_t> arguments) noexcept;
void RecordMaterialAppendExit(std::uintptr_t result) noexcept;

}  // namespace wonderbane::extension::terrain_material
