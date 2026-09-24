#pragma once
#include <atomic>
#include <cstdint>
namespace wonderbane::extension::furnishing {
// Registration is process-persistent. Unregistered optional preview has no effect.
// The renderer owns the persistent matrix imports. Notifications occur after the
// original GL call and carry the original game caller, never an adapter address.
inline std::atomic<void (*)(bool, std::uintptr_t) noexcept> matrix_event{nullptr};
inline void Matrix(bool push, std::uintptr_t caller) noexcept {
    if(auto f=matrix_event.load(std::memory_order_acquire)) { f(push,caller); }
}
inline std::atomic<bool> renderer_ready{false};
inline std::atomic<void (*)(bool) noexcept> renderer_event{nullptr};
inline std::atomic<void (*)(bool) noexcept> depth_clear_event{nullptr};
inline std::atomic<void (*)() noexcept> context_event{nullptr};
inline void Renderer(bool enabled) noexcept { renderer_ready.store(enabled,std::memory_order_release); if(auto f=renderer_event.load(std::memory_order_acquire)) { f(enabled); } }
inline void DepthClear(bool main) noexcept { if(auto f=depth_clear_event.load(std::memory_order_acquire)) { f(main); } }
inline void ContextLost() noexcept { if(auto f=context_event.load(std::memory_order_acquire)) { f(); } }
}
