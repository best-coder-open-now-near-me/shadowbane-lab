#pragma once
#include <Windows.h>
#include <atomic>
namespace wonderbane::extension {
// The existing native update owns this callback. It does not transfer movement
// grants: each service validates its own object, UI and operation authority.
using NativeOwnerService = void (*)(void*, HWND) noexcept;
inline std::atomic<NativeOwnerService> vendor_owner_service{nullptr};
inline void RunNativeOwnerServices(void* root, HWND window) noexcept {
    if (const auto service = vendor_owner_service.load(std::memory_order_acquire)) { service(root, window); }
}
}
