#pragma once
#include <Windows.h>
#include <array>
#include <cstdint>
namespace wonderbane::extension::movement {
struct NativeScene {
    std::uintptr_t actor = 0, parent = 0, world = 0, window = 0;
    std::array<std::uint32_t, 2> identity{};
    std::uint64_t epoch = 0;
};
// One process-pinned observer for the exact client. Start outside loader lock;
// Observe only from the admitted native-update callback on its owning thread.
// Unknown reference interfaces and replaced slots are explicitly unavailable.
bool StartNativeMovementLifetime(HWND) noexcept;
bool ObserveNativeMovementLifetime(void* native_window, NativeScene&) noexcept;
bool NativeMovementLifetimeCurrent(const NativeScene&) noexcept;
// Terminal retirement. Ordinary settings toggles must not retire this observer.
// Original call-through and callback records remain valid for process lifetime.
void RetireNativeMovementLifetime() noexcept;
}
