#pragma once
#include <Windows.h>
#include <cstdint>
#include "event_channel.h"
#include "movement_lifetime.h"

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
// Schema 2 adds passive input snapshots and a retained owner-loss event.
// Generation/scene and sampled keys contain no automation token or chat text.
struct alignas(8) MovementInputRecord {
    volatile LONG64 committed_sequence = 0;
    std::uint64_t tick_ms = 0, sample_tick_ms = 0, interval_ms = 0;
    std::uint64_t previous_generation = 0, generation = 0, scene = 0;
    std::uint32_t thread_id = 0, window = 0, previous_owner = 0, owner = 0;
    std::uint32_t reason = UINT32_MAX, kind = 1; // 1 snapshot, 2 revocation, 3 key decision
    std::uint32_t keys = 0, suppressed_keys = 0, original_keys = 0;
    std::uint32_t gates = 0, policy = 0, key_event = 0;
    // key_event: low3 bits direction index+1; down8, repeat16, consumed32.
    // A non-consumed event records forwarding decision, not remote execution.
};
static_assert(sizeof(MovementInputRecord) == 104);
// No-op when passive trace is disabled; never dispatches movement or input.
bool MovementInputTraceEnabled() noexcept;
void PublishMovementInputTrace(const MovementInputRecord&) noexcept;
struct alignas(8) MovementBoundaryTrace {
    char magic[8];
    std::uint32_t schema, record_size, capacity, process_id;
    std::uint64_t creation_filetime;
    volatile LONG64 write_sequence;
    volatile LONG dropped;
    volatile LONG enabled;
    volatile LONG64 input_write_sequence;
    MovementInputRecord input;
    MovementInputRecord last_owner_loss;
    MovementInputRecord input_events[256];
    MovementBoundaryRecord records[256];
    // Schema 3 appends bounded cause-only lifetime diagnostics; v2 offsets stay fixed.
    volatile LONG64 lifetime_published_tick;
    volatile LONG64 lifetime_write_sequence;
    movement::LifetimeRecord lifetime_current;
    movement::LifetimeRecord lifetime_first_invalidation;
    movement::LifetimeRecord lifetime_events[64];
};
static_assert(sizeof(MovementBoundaryRecord) == 72);
static_assert(offsetof(MovementBoundaryTrace, input_write_sequence) == 48);
static_assert(offsetof(MovementBoundaryTrace, input) == 56);
static_assert(offsetof(MovementBoundaryTrace, last_owner_loss) == 160);
static_assert(offsetof(MovementBoundaryTrace, input_events) == 264);
static_assert(offsetof(MovementBoundaryTrace, records) == 26888);
static_assert(offsetof(MovementBoundaryTrace, lifetime_published_tick) == 45320);
static_assert(offsetof(MovementBoundaryTrace, lifetime_current) == 45336);
static_assert(sizeof(MovementBoundaryTrace) == 50616);
} // namespace wonderbane::extension
