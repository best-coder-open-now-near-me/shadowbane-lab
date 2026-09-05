#pragma once
#include <Windows.h>
#include <cstdint>
#include "event_channel.h"

namespace wonderbane::extension {
// One verified native-update hook serves controls and optional passive tracing.
// The controls callback and all of its reachable state must remain process-pinned.
// It runs before the original native update; it must perform its own exact-window,
// scene and thread admission. It may retire itself only after native stop finishes.
using NativeMovementUpdate = void(*)(void* receiver, double delta) noexcept;
DWORD StartNativeMovementUpdates(const ProcessIdentity&, NativeMovementUpdate) noexcept;
void StopNativeMovementUpdates() noexcept;
// Passive observation never advertises movement capability or accepts commands.
DWORD StartMovementBoundaryTrace(const ProcessIdentity&) noexcept;
void StopMovementBoundaryTrace() noexcept;

struct alignas(8) MovementBoundaryRecord {
    volatile LONG64 committed_sequence;
    std::uint64_t tick_ms;
    double native_delta;
    std::uint32_t thread_id, foreground_thread, foreground_pid, receiver;
    std::uint32_t actor, game_mode, ui_candidate, modal_candidate;
    std::uint32_t path_count, movement_state, caller_rva, read_valid;
};
struct alignas(8) MovementBoundaryTrace {
    char magic[8];
    std::uint32_t schema, record_size, capacity, process_id;
    std::uint64_t creation_filetime;
    volatile LONG64 write_sequence;
    volatile LONG dropped;
    volatile LONG enabled;
    MovementBoundaryRecord records[256];
};
static_assert(sizeof(MovementBoundaryRecord) == 72);
static_assert(offsetof(MovementBoundaryTrace, records) == 48);
} // namespace wonderbane::extension
