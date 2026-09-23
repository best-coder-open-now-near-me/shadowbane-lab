#pragma once
#include "condemn_responses.h"
#include <cstring>
#include <map>
#include <memory>
#include <vector>
namespace wonderbane::extension::condemn::evidence {
inline bool Typed(Key k, unsigned type) noexcept { return k[0] && k[1] == type; }
inline bool KeyValid(Key k) noexcept { return (k[0] && k[1]) || k == Key{}; }
inline bool PayloadValid(const Payload& p) noexcept {
    const unsigned fields = p.operation == 14 || p.operation == 16 ? 3 : p.operation == 15 ? 5 : 1;
    if (p.operation < 11 || p.operation > 22 || p.fields != fields || p.state > 1 || p.inverted > 1
        || p.row_count > kRows || !KeyValid(p.building) || !KeyValid(p.entry)
        || !KeyValid(p.character) || !KeyValid(p.guild) || !KeyValid(p.nation)
        || (fields != 3 && p.scope)
        || (fields == 1 && (p.character != Key{} || p.guild != Key{} || p.nation != Key{}))) { return false; }
    for (std::size_t i = 0; i < p.rows.size(); ++i) {
        const auto& r = p.rows[i];
        if (i >= p.row_count) {
            const Row empty{};
            if (std::memcmp(&r, &empty, sizeof(r))) { return false; }
        } else if (r.flags > 0xffffff || !KeyValid(r.entry) || !KeyValid(r.character)
            || !KeyValid(r.guild) || !KeyValid(r.nation)) { return false; }
    }
    return true;
}
struct Proof {
    std::array<Record, 3> stages{};
    bool Enabled(Key building, Key entry) const noexcept {
        const auto& p = stages[0].payload;
        return Typed(building, 8) && Typed(entry, 23) && p.operation == 17 && !p.status
            && p.building == building && p.entry == entry && p.state == 1 && !p.inverted
            && !p.row_count && !p.reported_count;
    }
};
// One non-rearmable interval belonging to one process/scene. This validates
// response provenance only; scope, fresh owned row state and exclusive command
// admission remain separate requirements. Even Enabled does not assert a nonce.
class Window {
    struct Pending { std::array<Record, 2> stages{}; unsigned count = 0; };
    Cursor baseline_{}, current_{};
    std::uint64_t scene_ = 0, tick_ = 0;
    Key local_{};
    bool failed_ = false;
    std::map<std::uint64_t, std::unique_ptr<Pending>> pending_;
    bool RecordValid(const Record& r) const noexcept {
        if (r.sequence <= 0 || !r.thread_id || r.scene_epoch != scene_ || r.local != local_
            || !r.decode_sequence || r.stage < 1 || r.stage > 3 || !PayloadValid(r.payload)
            || r.tick_ms < tick_) { return false; }
        return r.stage == 1
            ? r.flags == 3 && r.decode_sequence == static_cast<std::uint64_t>(r.sequence)
                && r.caller_rva == 0x3625bc
            : r.flags == 7 && r.decode_sequence < static_cast<std::uint64_t>(r.sequence);
    }
public:
    Window(const Cursor& baseline, std::uint64_t scene, Key local) noexcept
        : baseline_(baseline), current_(baseline), scene_(scene), local_(local) {
        failed_ = !baseline.process_id || !baseline.creation || baseline.sequence > INT64_MAX
            || baseline.rejected > INT32_MAX || baseline.ticket_drops > INT64_MAX
            || !scene || !Typed(local, 53);
    }
    Window(const Window&) = delete;
    Window& operator=(const Window&) = delete;
    const Cursor& Current() const noexcept { return current_; }
    const Cursor& Baseline() const noexcept { return baseline_; }
    bool Healthy() const noexcept { return !failed_; }
    void Invalidate() noexcept { failed_ = true; pending_.clear(); }
    bool Consume(const Batch& batch, std::vector<Proof>& completed) noexcept {
        completed.clear();
        if (failed_) { return false; }
        const auto& next = batch.after;
        if (next.process_id != baseline_.process_id || next.creation != baseline_.creation
            || next.rejected != baseline_.rejected || next.ticket_drops != baseline_.ticket_drops
            || next.sequence < current_.sequence || next.sequence > INT64_MAX
            || batch.count > kCapacity || next.sequence - current_.sequence != batch.count) {
            Invalidate(); return false;
        }
        try {
            for (std::size_t i = 0; i < batch.count; ++i) {
                const auto& r = batch.records[i];
                if (r.sequence != static_cast<LONG64>(current_.sequence + i + 1) || !RecordValid(r)) {
                    Invalidate(); break;
                }
                tick_ = r.tick_ms;
                // Late processing of an old decode cannot complete new work.
                if (r.decode_sequence <= baseline_.sequence) { continue; }
                if (r.stage == 1) {
                    if (pending_.size() >= 64 || pending_.contains(r.decode_sequence)) { Invalidate(); break; }
                    auto p = std::make_unique<Pending>(); p->stages[0] = r; p->count = 1;
                    pending_.emplace(r.decode_sequence, std::move(p));
                    continue;
                }
                const auto it = pending_.find(r.decode_sequence);
                if (it == pending_.end() || it->second->count != r.stage - 1) { Invalidate(); break; }
                auto& p = *it->second;
                if (std::memcmp(&p.stages[0].payload, &r.payload, sizeof(Payload))) { Invalidate(); break; }
                if (r.stage == 2) { p.stages[1] = r; p.count = 2; continue; }
                if (r.thread_id != p.stages[1].thread_id || r.caller_rva != p.stages[1].caller_rva) {
                    Invalidate(); break;
                }
                // Allocate the large triple in the result vector, never on the owner stack.
                completed.emplace_back(); auto& proof = completed.back();
                proof.stages[0] = p.stages[0]; proof.stages[1] = p.stages[1]; proof.stages[2] = r;
                pending_.erase(it);
            }
            if (!failed_) { current_ = next; return true; }
        } catch (...) { Invalidate(); }
        // A later bad record invalidates all apparent completions from this drain.
        completed.clear(); return false;
    }
};
}
