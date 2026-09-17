#pragma once
#include "guard_funding_wire.h"
#include "movement_command_queue.h"
namespace wonderbane::extension::guard_funding {
struct QueuedCommand {
    std::uint64_t id = 0, sequence = 0, deadline = 0;
    wire::Verb verb{};
    wire::Command command{};
    // Reuse only the transport producer's process/heartbeat lease, never a
    // movement grant or movement permission.
    std::shared_ptr<movement::CommandLease> lease;
    std::atomic<unsigned> state{0};
    wire::Receipt receipt{};
    DWORD execution_thread = 0;
};
inline SRWLOCK queue_lock = SRWLOCK_INIT;
inline std::shared_ptr<QueuedCommand> queued;
inline bool Queue(const std::shared_ptr<QueuedCommand>& command) noexcept {
    AcquireSRWLockExclusive(&queue_lock);
    const bool vacant = !queued;
    if (vacant) { queued = command; }
    ReleaseSRWLockExclusive(&queue_lock); return vacant;
}
inline std::shared_ptr<QueuedCommand> Take() noexcept {
    AcquireSRWLockShared(&queue_lock); auto result = queued; ReleaseSRWLockShared(&queue_lock);
    unsigned pending = 0;
    if (!result || !result->state.compare_exchange_strong(pending, 1)) { return {}; }
    return result;
}
inline void Release(const std::shared_ptr<QueuedCommand>& command) noexcept {
    AcquireSRWLockExclusive(&queue_lock);
    if (queued == command) { queued.reset(); }
    ReleaseSRWLockExclusive(&queue_lock);
}
inline void Complete(const std::shared_ptr<QueuedCommand>& command, const wire::Receipt& receipt) noexcept {
    command->receipt = receipt; command->execution_thread = GetCurrentThreadId();
    command->state.store(2, std::memory_order_release);
}
}
