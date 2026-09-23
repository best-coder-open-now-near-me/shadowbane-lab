#pragma once
#include <Windows.h>
#include <mutex>

namespace wonderbane::extension {
// One admission boundary for scene hooks and owned-render callbacks. Shared
// nesting avoids lock inversion when an original render invokes GL hooks.
inline SRWLOCK g_render_lifetime = SRWLOCK_INIT;
inline std::recursive_mutex g_render_lifecycle;
inline thread_local unsigned g_render_callback_depth = 0;
inline thread_local unsigned g_render_mutation_depth = 0;
class RenderCallbackLease {
    bool owns_;
public:
    RenderCallbackLease() noexcept
        : owns_(g_render_callback_depth++ == 0 && g_render_mutation_depth == 0) {
        if (owns_) { AcquireSRWLockShared(&g_render_lifetime); }
    }
    ~RenderCallbackLease() {
        --g_render_callback_depth;
        if (owns_) { ReleaseSRWLockShared(&g_render_lifetime); }
    }
    RenderCallbackLease(const RenderCallbackLease&) = delete;
    RenderCallbackLease& operator=(const RenderCallbackLease&) = delete;
};
class RenderLifecycleMutation {
    std::lock_guard<std::recursive_mutex> lifecycle_;
    bool owns_;
public:
    RenderLifecycleMutation() noexcept
        : lifecycle_(g_render_lifecycle), owns_(g_render_mutation_depth++ == 0) {
        if (owns_) { AcquireSRWLockExclusive(&g_render_lifetime); }
    }
    ~RenderLifecycleMutation() {
        --g_render_mutation_depth;
        if (owns_) { ReleaseSRWLockExclusive(&g_render_lifetime); }
    }
    RenderLifecycleMutation(const RenderLifecycleMutation&) = delete;
    RenderLifecycleMutation& operator=(const RenderLifecycleMutation&) = delete;
};
}  // namespace wonderbane::extension
