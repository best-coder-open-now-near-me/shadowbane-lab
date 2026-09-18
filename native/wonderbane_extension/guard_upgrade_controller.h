#pragma once
#include "guard_upgrade_response.h"
#include <map>
namespace wonderbane::extension::guard_upgrade {
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Outcome Upgrade(const wire::Snapshot&) noexcept = 0;
    virtual wire::Outcome Reopen(const wire::Snapshot&, const ReturnSnapshot&) noexcept = 0;
};
class Controller {
    struct Record { wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    wire::Snapshot current_{};
    std::uint64_t revision_ = 0, deadline_ = 0;
    wire::Command transition_{};
    bool pending_ = false, unresolved_ = false;
    bool return_valid_ = false, reopen_attempted_ = false, reopened_ = false;
    ReturnSnapshot returned_{};
    std::uint32_t reopened_building_hud_ = 0;
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{};
        r.request = c.request; r.host = c.host; r.window = c.window;
        r.snapshot = current_; r.outcome = static_cast<unsigned>(outcome);
        r.transition_request = transition_.request;
        r.flags = (pending_ ? wire::in_flight : 0) | (unresolved_ ? wire::unresolved : 0)
            | (reopened_ ? wire::reopened : 0);
        if (ready && !Busy() && wire::ValidSnapshot(current_)) { r.flags |= wire::ready; }
        return r;
    }
public:
    bool Busy() const noexcept { return pending_ || unresolved_; }
    const wire::Snapshot& Current() const noexcept { return current_; }
    const wire::Snapshot* PendingReturn() const noexcept {
        return pending_ && !unresolved_ && !reopen_attempted_ ? &transition_.expected : nullptr;
    }
    void ObserveReturn(const ReturnSnapshot& s, bool valid) noexcept {
        return_valid_ = PendingReturn() && valid && CanReopen(transition_.expected, s);
        returned_ = return_valid_ ? s : ReturnSnapshot{};
    }
    void Observe(wire::Snapshot s, bool valid, std::uint64_t now) noexcept {
        s.navigation.revision = current_.navigation.revision;
        if (!valid || !wire::Equal(s, current_)) {
            if (revision_ == UINT64_MAX) { current_ = {}; unresolved_ = true; return; }
            s.navigation.revision = ++revision_;
        }
        current_ = valid ? s : wire::Snapshot{};
        if (!pending_ || unresolved_) { return; }
        const auto& before = transition_.expected;
        const bool same = reopened_
            ? wire::SameGuard(before, s) && s.navigation.building_hud == reopened_building_hud_
                && s.navigation.front_hud == s.navigation.vendor_hud
            : wire::SameOwner(before, s);
        if (now > deadline_ || (valid && !same)) {
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
        if (verb == wire::Verb::inspect) {
            // The original producer renews its lease via inspections. A different
            // process/generation cannot continue this transaction's UI work.
            if (PendingReturn() && return_valid_ && now <= deadline_
                && c.window == transition_.window
                && !std::memcmp(&c.host, &transition_.host, sizeof(c.host))) {
                reopen_attempted_ = true; // Never replay even an uncertain callback.
                reopened_building_hud_ = returned_.navigation.building_hud;
                const auto outcome = invoker.Reopen(transition_.expected, returned_);
                reopened_ = outcome == O::submitted;
                if (!reopened_) { unresolved_ = true; }
                return_valid_ = false;
            }
            return Receipt(c, O::observed, ready);
        }
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
            returned_ = {}; return_valid_ = reopen_attempted_ = reopened_ = false;
            reopened_building_hud_ = 0;
            const auto outcome = invoker.Upgrade(current_);
            if (outcome == O::stale || outcome == O::unavailable) { pending_ = false; }
            else if (outcome != O::submitted) { unresolved_ = true; }
            it->second.receipt = Receipt(c, outcome, false);
            return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
