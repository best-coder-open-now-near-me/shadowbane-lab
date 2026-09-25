#pragma once
#include <Windows.h>
#include <atomic>
#include "movement_lifetime.h"
#include "movement_controls.h"
namespace wonderbane::extension {
// The existing native update owns this callback. It does not transfer movement
// grants: each service validates its own object, UI and operation authority.
using NativeOwnerService = void (*)(void*, HWND) noexcept;
inline std::atomic<NativeOwnerService> vendor_owner_service{nullptr};
inline std::atomic<NativeOwnerService> combat_owner_service{nullptr};
using NativeOwnerStop = bool (*)(const movement::NativeScene&, const movement::Grant&, movement::StopReason) noexcept;
using NativeOwnerRetire = void (*)(std::uint64_t) noexcept;
// A stop callback completes before a replacement Grant is published. False keeps
// the old exact-Grant cleanup obligation and excludes every replacement writer.
inline std::atomic<NativeOwnerStop> combat_owner_stop{nullptr};
inline std::atomic<NativeOwnerRetire> combat_owner_retire{nullptr};
// Publish stop/retire before the update service. Call-through remains process-
// pinned: admitted activity retains both callbacks even after unregistering.
inline void RunNativeOwnerServices(void* root, HWND window) noexcept {
    if (const auto service = vendor_owner_service.load(std::memory_order_acquire)) { service(root, window); }
    if (const auto service = combat_owner_service.load(std::memory_order_acquire)) { service(root, window); }
}
}
