#pragma once
#include "guard_funding_wire.h"
#include <map>
namespace wonderbane::extension::guard_funding {
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Outcome Transfer(wire::Verb, const wire::Command&) noexcept = 0;
};
class Controller {
    struct Record { wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    std::array<wire::Snapshot, 2> current_{};
    std::uint64_t revision_ = 0, deadline_ = 0;
    wire::Command transition_{};
    wire::Verb transition_verb_ = wire::Verb::transfer;
    bool pending_ = false, unresolved_ = false;
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{}; r.request = c.request; r.host = c.host; r.window = c.window;
        if (wire::DirectionValid(c.direction)) { r.snapshot = current_[c.direction - 1]; }
        r.outcome = static_cast<unsigned>(outcome); r.transition_request = transition_.request;
        r.flags = (pending_ ? wire::in_flight : 0) | (unresolved_ ? wire::unresolved : 0);
        if (ready && !Busy() && wire::ValidSnapshot(r.snapshot)) { r.flags |= wire::ready; }
        return r;
    }
public:
    bool Busy() const noexcept { return pending_ || unresolved_; }
    bool NeedsObservation(std::uint32_t direction) const noexcept {
        return pending_ && !unresolved_ && transition_.direction == direction;
    }
    void Observe(std::uint32_t direction, wire::Snapshot s, bool valid, std::uint64_t now) noexcept {
        if (!wire::DirectionValid(direction)) { return; }
        auto& current = current_[direction - 1]; s.revision = current.revision;
        if (!valid || !wire::Equal(s, current)) {
            if (revision_ == UINT64_MAX) { current = {}; unresolved_ = true; return; }
            s.revision = ++revision_;
        }
        current = valid && s.direction == direction ? s : wire::Snapshot{};
        if (!NeedsObservation(direction)) { return; }
        const auto& before = transition_.expected;
        if (now > deadline_ || (valid && (!wire::SameOwner(before, s) || before.reserve != s.reserve))) {
            unresolved_ = true; return;
        }
        if (!valid) { return; }
        if (transition_verb_ == wire::Verb::open_quote) {
            if (s.balance != before.balance || s.purse != before.purse) { unresolved_ = true; return; }
            if (wire::Opened(transition_, s)) { pending_ = false; }
            return;
        }
        const auto balance = direction == 1 ? before.balance - transition_.amount : before.balance + transition_.amount;
        const auto purse = direction == 1 ? before.purse + transition_.amount : before.purse - transition_.amount;
        if ((s.balance != before.balance && s.balance != balance) || (s.purse != before.purse && s.purse != purse)) {
            unresolved_ = true; return;
        }
        if (wire::Confirmed(transition_, s)) { pending_ = false; }
    }
    wire::Receipt Execute(wire::Verb verb, const wire::Command& c,
        bool live, bool ready, std::uint64_t now, Invoker& invoker) noexcept {
        using O = wire::Outcome;
        if (!wire::Valid(verb, c)) { return Receipt(c, O::invalid, false); }
        if (!live) { return Receipt(c, O::stale, false); }
        if (verb == wire::Verb::inspect) { return Receipt(c, O::observed, ready); }
        const auto prior = records_.find(c.request);
        if (prior != records_.end()) {
            if (std::memcmp(&prior->second.command, &c, sizeof(c))) { return Receipt(c, O::invalid, false); }
            return prior->second.receipt;
        }
        if (Busy()) { return Receipt(c, O::pending, false); }
        const auto& current = current_[c.direction - 1];
        if (!ready || !wire::ValidSnapshot(current)) { return Receipt(c, O::unavailable, false); }
        if (!wire::Equal(c.expected, current)) { return Receipt(c, O::stale, true); }
        if (verb == wire::Verb::transfer ? !wire::Eligible(current, c.amount) : !wire::EligibleOpen(current)) { return Receipt(c, O::invalid, true); }
        if (records_.size() >= 4096 || now > UINT64_MAX - 15000) { return Receipt(c, O::exhausted, false); }
        try {
            auto [it, inserted] = records_.emplace(c.request, Record{c, Receipt(c, O::uncertain, false)});
            if (!inserted) { return Receipt(c, O::invalid, false); }
            transition_ = c; transition_verb_ = verb; pending_ = true; deadline_ = now + 15000;
            const auto outcome = invoker.Transfer(verb, c);
            if (outcome == O::stale || outcome == O::unavailable) { pending_ = false; }
            else if (outcome != O::submitted) { unresolved_ = true; }
            it->second.receipt = Receipt(c, outcome, false); return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
