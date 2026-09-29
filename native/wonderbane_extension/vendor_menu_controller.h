#pragma once
#include "vendor_menu_wire.h"
#include <map>
namespace wonderbane::extension::vendor_menu {
inline constexpr std::uint64_t response_timeout_ms = 5000;
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Outcome Invoke(wire::Verb, const wire::Command&) noexcept = 0;
};
class Controller {
    struct Record { wire::Verb verb; wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    Record* pending_ = nullptr;
    wire::Snapshot current_{};
    std::uint64_t revision_ = 0, deadline_ = 0;
    bool unresolved_ = false;
    std::array<std::uint8_t, 16> transition_{};
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{}; r.request = c.request; r.host = c.host; r.window = c.window;
        r.outcome = static_cast<unsigned>(outcome); r.snapshot = current_; r.transition_request = transition_;
        r.flags = (pending_ ? wire::in_flight : 0) | (unresolved_ ? wire::unresolved : 0)
            | (ready && !Busy() && wire::ValidSnapshot(current_) ? wire::ready : 0);
        return r;
    }
public:
    bool Busy() const noexcept { return pending_ || unresolved_; }
    const wire::Snapshot& Current() const noexcept { return current_; }
    void Observe(wire::Snapshot s, bool valid, std::uint64_t now) noexcept {
        s.revision = current_.revision;
        if (!valid || !wire::Equal(s, current_)) {
            if (revision_ == UINT64_MAX) { current_ = {}; unresolved_ = true; return; }
            s.revision = ++revision_;
        }
        current_ = valid ? s : wire::Snapshot{};
        if (!pending_ || unresolved_) { return; }
        const bool same_recipe_required = pending_->verb == wire::Verb::select_recipe
            || pending_->verb == wire::Verb::random_mode;
        const bool replaced_recipe = valid && same_recipe_required
            && (s.recipe != pending_->command.expected.recipe
                || s.recipe_list != pending_->command.expected.recipe_list);
        if (now > deadline_ || replaced_recipe || (valid && !wire::SameOwner(pending_->command.expected, s))) {
            unresolved_ = true;
        } else if (valid && wire::Reached(pending_->verb, pending_->command, s)) {
            transition_ = pending_->command.request; pending_ = nullptr;
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
            return prior->second.receipt;
        }
        if (Busy()) { return Receipt(c, O::pending, false); }
        if (!ready || !wire::ValidSnapshot(current_)) { return Receipt(c, O::unavailable, false); }
        if (!wire::Equal(c.expected, current_)) { return Receipt(c, O::stale, true); }
        if (records_.size() >= 4096 || now > UINT64_MAX - response_timeout_ms) { return Receipt(c, O::exhausted, false); }
        try {
            auto [it, inserted] = records_.emplace(c.request, Record{verb, c, Receipt(c, O::uncertain, false)});
            if (!inserted) { return Receipt(c, O::invalid, false); }
            auto outcome = O::observed;
            if (wire::Reached(verb, c, current_)) { transition_ = c.request; }
            else {
                pending_ = &it->second; deadline_ = now + response_timeout_ms;
                outcome = invoker.Invoke(verb, c);
                if (outcome == O::stale || outcome == O::unavailable || outcome == O::invalid) { pending_ = nullptr; }
                else if (outcome != O::submitted) { unresolved_ = true; }
            }
            it->second.receipt = Receipt(c, outcome, outcome == O::observed);
            return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
