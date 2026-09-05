#pragma once
#include <Windows.h>
#include <cstdint>
#include "event_channel.h"

namespace wonderbane::extension {
// Passive investigation only. Never advertises movement capability or accepts commands.
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
