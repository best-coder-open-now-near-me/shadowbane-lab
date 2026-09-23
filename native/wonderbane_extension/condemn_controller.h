#pragma once
#include "condemn_evidence.h"
#include "condemn_wire.h"
namespace wonderbane::extension::condemn {
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual bool Baseline(Cursor&) noexcept = 0;
    virtual native::Result Invoke(native::Action, const native::Target&, const native::Snapshot&) noexcept = 0;
};
class Controller {
    struct Retained { wire::Command command{}; wire::Receipt receipt{}; };
    std::map<std::array<std::uint8_t, 16>, Retained> records_;
    native::Snapshot native_{};
    wire::Snapshot current_{};
    wire::Target current_target_{};
    wire::Command transition_{};
    wire::Phase phase_ = wire::Phase::idle;
    std::unique_ptr<evidence::Window> evidence_;
    std::vector<evidence::Proof> completed_;
    std::uint64_t revision_ = 0, deadline_ = 0, last_now_ = 0;
    std::uint64_t action_tick_ = 0, floor_ = 0, proof_sequence_ = 0, proof_tick_ = 0;
    wire::Snapshot action_owner_{};
    bool pending_ = false, unresolved_ = false;
    void Fail() noexcept {
        unresolved_ = true; phase_ = wire::Phase::uncertain;
        if (evidence_) { evidence_->Invalidate(); }
    }
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{};
        r.request = c.request; r.host = c.host; r.window = c.window; r.outcome = static_cast<unsigned>(outcome);
        r.flags = (pending_ ? wire::in_flight : 0) | (unresolved_ ? wire::unresolved : 0);
        if (ready && !Busy() && current_target_ == c.target && wire::Eligible(c.target, current_)) { r.flags |= wire::ready; }
        r.snapshot = current_; r.target = current_target_;
        r.transition_target = transition_.target; r.transition_request = transition_.request; r.phase = static_cast<unsigned>(phase_);
        r.action_tick = action_tick_; r.response_floor = floor_; r.completion_sequence = proof_sequence_;
        return r;
    }
    bool SameOwner(const wire::Snapshot& s) const noexcept {
        const auto& b = transition_.expected;
        return s.scene == b.scene && s.local == b.local && s.root == b.root
            && s.manager == b.manager && s.building_hud == b.building_hud && s.building == b.building;
    }
    wire::Outcome Act(native::Action action, std::uint64_t now, Invoker& invoker, bool initial) noexcept {
        Cursor cursor{};
        // Never skip responses that arrived since the owner's last drain. A later
        // inspection can proceed after that drain; this is not a retry of an action.
        if (!invoker.Baseline(cursor) || !evidence_ || !evidence_->Healthy()) { Fail(); return wire::Outcome::uncertain; }
        const auto& before = evidence_->Current();
        if (cursor != before) {
            if (cursor.process_id != before.process_id || cursor.creation != before.creation
                || cursor.rejected != before.rejected || cursor.ticket_drops != before.ticket_drops
                || cursor.sequence < before.sequence || cursor.sequence - before.sequence > kCapacity) { Fail(); }
            return unresolved_ ? wire::Outcome::uncertain : wire::Outcome::pending;
        }
        action_tick_ = now; floor_ = cursor.sequence; action_owner_ = current_;
        phase_ = action == native::Action::open ? wire::Phase::opening
            : action == native::Action::add ? wire::Phase::adding : wire::Phase::enabling;
        const auto result = invoker.Invoke(action, wire::Decode(transition_.target), native_);
        if (result == native::Result::submitted) { return wire::Outcome::submitted; }
        if (initial && result == native::Result::unavailable) {
            pending_ = false; phase_ = wire::Phase::idle; evidence_.reset(); return wire::Outcome::unavailable;
        }
        Fail(); return wire::Outcome::uncertain;
    }
    wire::Outcome Advance(std::uint64_t now, Invoker& invoker, bool initial) noexcept {
        using A = native::Action;
        const auto& t = transition_.target;
        if (phase_ == wire::Phase::idle && current_.front == current_.building_hud && current_.open_button) { return Act(A::open, now, invoker, true); }
        if (!wire::List(t, current_)) { return wire::Outcome::pending; }
        if (phase_ == wire::Phase::enabling) { return wire::Outcome::pending; }
        if (current_.entry) {
            if (current_.enabled) {
                // Existing state is a distinct read-only result. An enabled row
                // appearing during Add is not proof that our composite completed.
                if (phase_ != wire::Phase::idle && phase_ != wire::Phase::opening) { Fail(); return wire::Outcome::uncertain; }
                pending_ = false; phase_ = wire::Phase::existing; return wire::Outcome::observed;
            }
            return Act(A::enable, now, invoker, initial);
        }
        if (phase_ == wire::Phase::adding) { return wire::Outcome::pending; }
        if (current_.count >= 512) { Fail(); return wire::Outcome::uncertain; }
        return Act(A::add, now, invoker, initial);
    }
public:
    bool Busy() const noexcept { return pending_ || unresolved_; }
    const wire::Target* ActiveTarget() const noexcept { return Busy() ? &transition_.target : nullptr; }
    const Cursor* ResponseCursor() const noexcept { return pending_ && !unresolved_ && evidence_ ? &evidence_->Current() : nullptr; }
    void Observe(const wire::Target& target, const native::Snapshot& s, bool valid, const Batch* batch, std::uint64_t now) noexcept {
        auto next = wire::Encode(s, current_.revision);
        if (!valid || target != current_target_ || !wire::Equal(next, current_)) {
            if (revision_ == UINT64_MAX) { current_ = {}; Fail(); return; }
            next.revision = ++revision_;
        }
        current_target_ = target;
        native_ = valid ? s : native::Snapshot{};
        current_ = valid ? next : wire::Snapshot{};
        if (!pending_ || unresolved_) { return; }
        if (target != transition_.target || now < last_now_ || now > deadline_ || !batch || !evidence_->Consume(*batch, completed_)
            || (batch->count && batch->records[batch->count - 1].tick_ms > now)) { Fail(); return; }
        last_now_ = now;
        if (valid && !SameOwner(current_)) { Fail(); return; }
        if (phase_ == wire::Phase::enabling) {
            for (const auto& proof : completed_) {
                const auto& first = proof.stages[0]; const auto& last = proof.stages[2];
                if (last.tick_ms > now) { Fail(); return; }
                if (first.payload.operation != 17 || first.payload.building != transition_.target.building
                    || first.payload.entry != action_owner_.entry_key || first.decode_sequence <= floor_
                    || first.tick_ms < action_tick_) { continue; }
                if (!proof.Enabled(transition_.target.building, action_owner_.entry_key)) { Fail(); return; }
                proof_sequence_ = static_cast<std::uint64_t>(last.sequence); proof_tick_ = last.tick_ms;
            }
        }
        if (!valid) { return; }
        if (phase_ == wire::Phase::adding || phase_ == wire::Phase::enabling) {
            if (!wire::List(transition_.target, current_) || current_.kos != action_owner_.kos
                || current_.list != action_owner_.list) { Fail(); return; }
        }
        if (phase_ == wire::Phase::enabling) {
            if (current_.entry_key != action_owner_.entry_key || current_.row != action_owner_.row
                || current_.entry != action_owner_.entry) { Fail(); return; }
            if (proof_sequence_ && current_.enabled && now >= proof_tick_) {
                pending_ = false; phase_ = wire::Phase::verified;
            }
        }
    }
    wire::Receipt Execute(wire::Verb verb, const wire::Command& c, bool live, bool ready,
        std::uint64_t now, Invoker& invoker) noexcept {
        using O = wire::Outcome;
        if (!wire::Valid(verb, c)) { return Receipt(c, O::invalid, false); }
        if (!live) { return Receipt(c, O::stale, false); }
        if (verb == wire::Verb::inspect) {
            if (pending_ && !unresolved_ && ready && current_target_ == c.target && c.target == transition_.target
                && c.transition_request == transition_.request && c.window == transition_.window
                && !std::memcmp(&c.host, &transition_.host, sizeof(c.host))) {
                if (now < last_now_ || now > deadline_) { Fail(); }
                else { (void)Advance(now, invoker, false); }
            }
            return Receipt(c, O::observed, ready);
        }
        const auto old = records_.find(c.request);
        if (old != records_.end()) {
            return std::memcmp(&old->second.command, &c, sizeof(c))
                ? Receipt(c, O::invalid, false) : old->second.receipt;
        }
        if (Busy()) { return Receipt(c, O::pending, false); }
        if (!ready || current_target_ != c.target || !wire::Eligible(c.target, current_)) { return Receipt(c, O::unavailable, false); }
        if (!wire::Equal(c.expected, current_)) { return Receipt(c, O::stale, true); }
        if (records_.size() >= 4096 || now > UINT64_MAX - 45000) { return Receipt(c, O::exhausted, false); }
        try {
            Cursor cursor{};
            if (!invoker.Baseline(cursor)) { return Receipt(c, O::unavailable, false); }
            auto interval = std::make_unique<evidence::Window>(cursor, current_.scene, current_.local);
            if (!interval->Healthy()) { return Receipt(c, O::unavailable, false); }
            auto [it, inserted] = records_.emplace(c.request, Retained{c, Receipt(c, O::uncertain, false)});
            if (!inserted) { return Receipt(c, O::invalid, false); }
            evidence_ = std::move(interval); transition_ = c; pending_ = true;
            deadline_ = now + 45000; last_now_ = now; action_tick_ = floor_ = proof_sequence_ = proof_tick_ = 0;
            action_owner_ = {}; phase_ = wire::Phase::idle;
            const auto outcome = Advance(now, invoker, true);
            it->second.receipt = Receipt(c, outcome, false);
            return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
