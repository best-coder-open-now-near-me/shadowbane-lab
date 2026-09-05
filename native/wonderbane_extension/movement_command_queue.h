#pragma once
#include "movement_wire.h"
#include <Windows.h>
#include <atomic>
#include <memory>

namespace wonderbane::extension::movement {
// Storage referenced by validate is process-pinned after successful channel
// startup. Neither callbacks nor the owning update acquire the producer mutex.
struct CommandLease {
    std::shared_ptr<void> backing;
    HANDLE process = nullptr;
    wire::Host host{};
    void* context = nullptr;
    bool (*validate)(void*, const wire::Host&, std::uint64_t) noexcept = nullptr;
    ~CommandLease() { if (process) { CloseHandle(process); } }
    bool Current(std::uint64_t now) const noexcept {
        return process && WaitForSingleObject(process, 0) == WAIT_TIMEOUT
            && validate && validate(context, host, now);
    }
};
struct QueuedCommand {
    std::uint64_t id = 0, sequence = 0, deadline = 0;
    wire::Verb verb{}; wire::Command command{};
    std::shared_ptr<CommandLease> lease;
    // 0 queued, 1 owning thread executing, 2 immutable receipt published.
    std::atomic<unsigned> state{0};
    wire::Receipt receipt{};
    DWORD execution_thread = 0;
};
namespace command_queue_detail {
inline SRWLOCK lock = SRWLOCK_INIT;
inline std::shared_ptr<QueuedCommand> pending;
}
inline bool QueueMovementCommand(const std::shared_ptr<QueuedCommand>& command) noexcept {
    AcquireSRWLockExclusive(&command_queue_detail::lock);
    const bool vacant = !command_queue_detail::pending;
    if (vacant) { command_queue_detail::pending = command; }
    ReleaseSRWLockExclusive(&command_queue_detail::lock); return vacant;
}
inline std::shared_ptr<QueuedCommand> TakeMovementCommand() noexcept {
    AcquireSRWLockShared(&command_queue_detail::lock);
    auto command = command_queue_detail::pending;
    ReleaseSRWLockShared(&command_queue_detail::lock);
    unsigned queued = 0;
    if (!command || !command->state.compare_exchange_strong(queued, 1)) { return {}; }
    return command;
}
inline void ReleaseMovementCommand(const std::shared_ptr<QueuedCommand>& command) noexcept {
    AcquireSRWLockExclusive(&command_queue_detail::lock);
    if (command_queue_detail::pending == command) { command_queue_detail::pending.reset(); }
    ReleaseSRWLockExclusive(&command_queue_detail::lock);
}
inline void CompleteMovementCommand(const std::shared_ptr<QueuedCommand>& command,
    const wire::Receipt& receipt) noexcept {
    command->receipt = receipt; command->execution_thread = GetCurrentThreadId();
    command->state.store(2, std::memory_order_release);
}
} // namespace wonderbane::extension::movement
