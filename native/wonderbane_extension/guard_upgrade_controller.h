#pragma once
#include "guard_upgrade_wire.h"
#include <map>
namespace wonderbane::extension::guard_upgrade {
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Outcome Upgrade(const wire::Snapshot&) noexcept = 0;
};
class Controller {
    struct Record { wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    wire::Snapshot current_{};
    std::uint64_t revision_ = 0, deadline_ = 0;
    wire::Command transition_{};
    bool pending_ = false, unresolved_ = false;
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{};
        r.request = c.request; r.host = c.host; r.window = c.window;
        r.snapshot = current_; r.outcome = static_cast<unsigned>(outcome);
        r.transition_request = transition_.request;
        r.flags = (pending_ ? wire::in_flight : 0) | (unresolved_ ? wire::unresolved : 0);
        if (ready && !Busy() && wire::ValidSnapshot(current_)) { r.flags |= wire::ready; }
        return r;
    }
public:
    bool Busy() const noexcept { return pending_ || unresolved_; }
    const wire::Snapshot& Current() const noexcept { return current_; }
    void Observe(wire::Snapshot s, bool valid, std::uint64_t now) noexcept {
        s.navigation.revision = current_.navigation.revision;
        if (!valid || !wire::Equal(s, current_)) {
            if (revision_ == UINT64_MAX) { current_ = {}; unresolved_ = true; return; }
            s.navigation.revision = ++revision_;
        }
        current_ = valid ? s : wire::Snapshot{};
        if (!pending_ || unresolved_) { return; }
        const auto& before = transition_.expected;
        if (now > deadline_ || (valid && !wire::SameOwner(before, s))) {
            unresolved_ = true; return;
        }
        if (!valid) { return; } // Brief missing response does not prove failure.
        if (s.rank < before.rank || s.rank > before.rank + 1
            || (s.funds != before.funds && s.funds != before.funds - before.cost)) {
            unresolved_ = true; return;
        }
        // Both independent observations are required; neither alone confirms spending.
        if (s.funds == before.funds - before.cost
            && ((s.rank == before.rank && s.upgrading && (s.control_flags & 4))
                || s.rank == before.rank + 1)) {
            pending_ = false;
        }
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
            return prior->second.receipt; // Never resubmit, including stale/uncertain attempts.
        }
        if (Busy()) { return Receipt(c, O::pending, false); }
        if (!ready || !wire::ValidSnapshot(current_)) { return Receipt(c, O::unavailable, false); }
        if (!wire::Equal(c.expected, current_)) { return Receipt(c, O::stale, true); }
        if (!wire::Eligible(current_)) { return Receipt(c, O::invalid, true); }
        if (records_.size() >= 4096 || now > UINT64_MAX - 15000) { return Receipt(c, O::exhausted, false); }
        try {
            auto [it, inserted] = records_.emplace(c.request, Record{c, Receipt(c, O::uncertain, false)});
            if (!inserted) { return Receipt(c, O::invalid, false); }
            transition_ = c; pending_ = true; deadline_ = now + 15000;
            const auto outcome = invoker.Upgrade(current_);
            if (outcome == O::stale || outcome == O::unavailable) { pending_ = false; }
            else if (outcome != O::submitted) { unresolved_ = true; }
            it->second.receipt = Receipt(c, outcome, false);
            return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
