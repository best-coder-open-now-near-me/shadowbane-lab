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
// Optional passive diagnostics contain causes/masks only, never native values.
enum class LifetimeCause : std::uint32_t {
    stable = 1, first_watch, tuple_changed, capture_failed, capture_changed,
    reference_notice, world_notice, binding_lost, arm_rejected, terminal, exhausted, rearmed
};
enum class LifetimeStage : std::uint32_t {
    none, window, receiver, mode, actor, world, identity, position, pose, parent,
    unrecorded_callbacks, overlapping_callback, matching_destruction, reference, binding
};
struct alignas(8) LifetimeRecord {
    std::uint64_t sequence = 0, tick_ms = 0, previous_epoch = 0, epoch = 0;
    std::uint64_t observed_epoch = 0, watch_generation = 0;
    std::uint32_t cause = 0, outcome = 0, failure_stage = 0, changed_fields = 0;
    std::uint32_t valid_fields = 0, notice_role = 0, finalizer_flags = 0, thread_id = 0;
    // outcome: 0 asynchronous notice, 1 rejected observation, 2 accepted observation.
    // fields: actor1,parent2,world4,window8,identity-low16,identity-high32.
    // notice_role: actor1,parent2,world4; flags only for reference finalizers.
};
static_assert(sizeof(LifetimeRecord) == 80);
struct LifetimeDiagnostics {
    std::uint64_t write_sequence = 0;
    LifetimeRecord current{}, first_invalidation{};
    std::array<LifetimeRecord, 64> events{};
};
void EnableNativeMovementLifetimeDiagnostics(bool) noexcept;
// Nonblocking snapshot; callers must never publish while holding observer lock.
bool ReadNativeMovementLifetimeDiagnostics(LifetimeDiagnostics&) noexcept;
// One process-pinned observer for the exact client. Start outside loader lock;
// Observe only from the admitted native-update callback on its owning thread.
// Unknown reference interfaces and replaced slots are explicitly unavailable.
bool StartNativeMovementLifetime(HWND) noexcept;
bool ObserveNativeMovementLifetime(void* native_window, NativeScene&) noexcept;
bool NativeMovementLifetimeCurrent(const NativeScene&) noexcept;
// Proves a direct, fully verified parent-only publication from an alive watch.
// Destruction/capture gaps invalidate this proof; it never authorizes old targets.
bool NativeMovementParentTransition(const NativeScene& previous, const NativeScene& current) noexcept;
// Terminal retirement. Ordinary settings toggles must not retire this observer.
// Original call-through and callback records remain valid for process lifetime.
void RetireNativeMovementLifetime() noexcept;
}
