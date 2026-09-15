#pragma once
#include "vendor_navigation_wire.h"
#include <map>
namespace wonderbane::extension::vendor_navigation {
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Outcome Open(wire::Verb, const wire::Command&) noexcept = 0;
};
class Controller {
    struct Record { wire::Verb verb; wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    wire::Snapshot current_{};
    std::uint64_t revision_ = 0, response_deadline_ = 0;
    wire::Command transition_{};
    wire::Verb transition_verb_{};
    bool pending_ = false, unresolved_ = false;
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{};
        r.request = c.request; r.host = c.host; r.window = c.window;
        r.snapshot = current_; r.outcome = static_cast<unsigned>(outcome);
        r.transition_request = transition_.request;
        r.flags = pending_ ? wire::in_flight : 0;
        if (unresolved_) { r.flags |= wire::unresolved; }
        if (ready && !Busy() && wire::ValidSnapshot(current_) && !current_.offline) { r.flags |= wire::ready; }
        return r;
    }
public:
    const wire::Snapshot& Current() const noexcept { return current_; }
    bool Busy() const noexcept { return pending_ || unresolved_; }
    void Observe(wire::Snapshot s, bool valid, std::uint64_t now) noexcept {
        s.revision = current_.revision;
        if (!valid || !wire::Equal(s, current_)) {
            if (revision_ == UINT64_MAX) { current_ = {}; unresolved_ = true; return; }
            s.revision = ++revision_;
        }
        current_ = valid ? s : wire::Snapshot{};
        if (pending_ && !unresolved_) {
            if (now > response_deadline_ || (valid && s.scene != transition_.expected.scene)) {
                unresolved_ = true;
            } else if (valid && wire::Opened(s, transition_verb_, transition_.building, transition_.vendor)) {
                pending_ = false;
            }
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
            if (prior->second.verb != verb || std::memcmp(&prior->second.command, &c, sizeof(c))) {
                return Receipt(c, O::invalid, false);
            }
            return prior->second.receipt; // Immutable original receipt; never replay.
        }
        if (Busy()) { return Receipt(c, O::pending, false); }
        if (!ready || !wire::ValidSnapshot(current_)) { return Receipt(c, O::unavailable, false); }
        if (!wire::Equal(c.expected, current_)) { return Receipt(c, O::stale, true); }
        if (records_.size() >= 4096 || now > UINT64_MAX - 10000) { return Receipt(c, O::exhausted, false); }
        try {
            auto [it, inserted] = records_.emplace(c.request, Record{verb, c, Receipt(c, O::uncertain, false)});
            if (!inserted) { return Receipt(c, O::invalid, false); }
            const auto outcome = wire::Opened(current_, verb, c.building, c.vendor)
                ? O::observed : invoker.Open(verb, c);
            transition_ = c; transition_verb_ = verb;
            if (outcome == O::submitted || outcome == O::uncertain) {
                pending_ = true; unresolved_ = outcome == O::uncertain; response_deadline_ = now + 10000;
            }
            it->second.receipt = Receipt(c, outcome, outcome == O::observed);
            return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
