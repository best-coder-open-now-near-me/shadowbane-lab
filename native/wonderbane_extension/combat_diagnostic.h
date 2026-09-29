#pragma once
#include "combat_wire.h"
#include <cstdio>

namespace wonderbane::extension::combat {
// Diagnostic-only local execution evidence. Never grants admission or proves cleanup.
// Kept outside Receipt so its strict v1 wire contract and reserved bytes stay unchanged.
enum class Stage : unsigned {
    none, runtime_ready, binding, fence_open, owner_current, owner_begin, baseline_pause,
    baseline_current, owner_repin, target_admission, party_snapshot, party_protection,
    initial_current, actor_retain, position, query_construct, query_current, query,
    query_match, target_identity, selection_retain, selection_current, selection,
    selection_recheck, fence_enter, entry_recheck, writer, dispatch, post_dispatch,
    active_state, no_entry
};
struct Diagnostic {
    Stage stage = Stage::none;
    wire::Outcome outcome = wire::Outcome::unavailable;
    bool dispatched = false, native_entered = false, appended = false, followup_entered = false;
    // Exact movement::Result when a movement owner/baseline call rejected; -1 = not observed.
    int movement_result = -1;
};
inline const char* StageName(Stage stage) noexcept {
    switch (stage) {
#define WB_COMBAT_STAGE(value) case Stage::value: return #value;
        WB_COMBAT_STAGE(none) WB_COMBAT_STAGE(runtime_ready) WB_COMBAT_STAGE(binding)
        WB_COMBAT_STAGE(fence_open) WB_COMBAT_STAGE(owner_current) WB_COMBAT_STAGE(owner_begin)
        WB_COMBAT_STAGE(baseline_pause) WB_COMBAT_STAGE(baseline_current) WB_COMBAT_STAGE(owner_repin)
        WB_COMBAT_STAGE(target_admission) WB_COMBAT_STAGE(party_snapshot) WB_COMBAT_STAGE(party_protection)
        WB_COMBAT_STAGE(initial_current) WB_COMBAT_STAGE(actor_retain) WB_COMBAT_STAGE(position)
        WB_COMBAT_STAGE(query_construct) WB_COMBAT_STAGE(query_current) WB_COMBAT_STAGE(query)
        WB_COMBAT_STAGE(query_match) WB_COMBAT_STAGE(target_identity) WB_COMBAT_STAGE(selection_retain)
        WB_COMBAT_STAGE(selection_current) WB_COMBAT_STAGE(selection) WB_COMBAT_STAGE(selection_recheck)
        WB_COMBAT_STAGE(fence_enter) WB_COMBAT_STAGE(entry_recheck) WB_COMBAT_STAGE(writer)
        WB_COMBAT_STAGE(dispatch) WB_COMBAT_STAGE(post_dispatch) WB_COMBAT_STAGE(active_state)
        WB_COMBAT_STAGE(no_entry)
#undef WB_COMBAT_STAGE
    }
    return "unknown";
}
inline const char* OutcomeName(wire::Outcome outcome) noexcept {
    switch (outcome) {
#define WB_COMBAT_OUTCOME(value) case wire::Outcome::value: return #value;
        WB_COMBAT_OUTCOME(observed) WB_COMBAT_OUTCOME(client_outbound_queued)
        WB_COMBAT_OUTCOME(stale) WB_COMBAT_OUTCOME(unavailable) WB_COMBAT_OUTCOME(invalid)
        WB_COMBAT_OUTCOME(pending) WB_COMBAT_OUTCOME(uncertain) WB_COMBAT_OUTCOME(exhausted)
        WB_COMBAT_OUTCOME(local_cancelled) WB_COMBAT_OUTCOME(native_rejected)
#undef WB_COMBAT_OUTCOME
    }
    return "unknown";
}
inline std::size_t FormatDiagnostic(const Diagnostic& value, char (&out)[73]) noexcept {
    const int length = value.stage == Stage::none
        ? std::snprintf(out, sizeof(out), "native_combat_receipt_v1")
        : std::snprintf(out, sizeof(out), "combat_v1:%s:%s:d%un%uq%uf%u:m%d", StageName(value.stage),
            OutcomeName(value.outcome), static_cast<unsigned>(value.dispatched),
            static_cast<unsigned>(value.native_entered), static_cast<unsigned>(value.appended),
            static_cast<unsigned>(value.followup_entered), value.movement_result);
    return length > 0 && length <= 72 ? static_cast<std::size_t>(length) : 0;
}
}
