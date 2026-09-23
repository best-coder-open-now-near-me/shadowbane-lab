#pragma once
#include "city_window_wire.h"
#include <map>
namespace wonderbane::extension::city_window {
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Outcome Open(const wire::Snapshot&) noexcept = 0;
};
class Controller {
    struct Record { wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    wire::Snapshot current_{};
    std::uint64_t revision_ = 0;
    wire::Receipt Receipt(const wire::Command& c, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt r{};
        r.request = c.request; r.host = c.host; r.window = c.window;
        r.snapshot = current_; r.outcome = static_cast<unsigned>(outcome);
        r.flags = ready && wire::ValidSnapshot(current_) && !current_.loading ? wire::ready : 0;
        return r;
    }
public:
    const wire::Snapshot& Current() const noexcept { return current_; }
    void Observe(wire::Snapshot s, bool valid) noexcept {
        s.revision = current_.revision;
        if (!valid || !wire::Equal(s, current_)) {
            if (revision_ == UINT64_MAX) { current_ = {}; return; }
            s.revision = ++revision_;
        }
        current_ = valid ? s : wire::Snapshot{};
    }
    wire::Receipt Execute(wire::Verb verb, const wire::Command& c,
        bool live, bool ready, Invoker& invoker) noexcept {
        using O = wire::Outcome;
        if (!wire::Valid(verb, c)) { return Receipt(c, O::invalid, false); }
        if (!live) { return Receipt(c, O::stale, false); }
        if (verb == wire::Verb::inspect) { return Receipt(c, O::observed, ready); }
        auto prior = records_.find(c.request);
        if (prior != records_.end()) {
            if (std::memcmp(&prior->second.command, &c, sizeof(c))) { return Receipt(c, O::invalid, false); }
            return prior->second.receipt;
        }
        if (!ready || !wire::ValidSnapshot(current_)) { return Receipt(c, O::unavailable, false); }
        if (!wire::Equal(c.expected, current_)) { return Receipt(c, O::stale, ready); }
        if (current_.loading) { return Receipt(c, O::pending, false); }
        if (records_.size() >= 4096) { return Receipt(c, O::exhausted, false); }
        try {
            auto [it, inserted] = records_.emplace(c.request, Record{c, Receipt(c, O::uncertain, false)});
            if (!inserted) { return Receipt(c, O::invalid, false); }
            // Already open is a no-op. It does not claim a new server response.
            const auto outcome = current_.visible && current_.active_manager == current_.manager
                ? O::observed : invoker.Open(current_);
            it->second.receipt = Receipt(c, outcome, outcome == O::observed);
            return it->second.receipt;
        } catch (...) { return Receipt(c, O::unavailable, false); }
    }
};
}
