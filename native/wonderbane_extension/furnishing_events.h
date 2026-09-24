#pragma once
#include <atomic>
namespace wonderbane::extension::furnishing {
// Registration is process-persistent. Unregistered optional preview has no effect.
inline std::atomic<bool> renderer_ready{false};
inline std::atomic<void (*)(bool) noexcept> renderer_event{nullptr};
inline std::atomic<void (*)(bool) noexcept> depth_clear_event{nullptr};
inline std::atomic<void (*)() noexcept> context_event{nullptr};
inline void Renderer(bool enabled) noexcept { renderer_ready.store(enabled,std::memory_order_release); if(auto f=renderer_event.load(std::memory_order_acquire)) { f(enabled); } }
inline void DepthClear(bool main) noexcept { if(auto f=depth_clear_event.load(std::memory_order_acquire)) { f(main); } }
inline void ContextLost() noexcept { if(auto f=context_event.load(std::memory_order_acquire)) { f(); } }
}
