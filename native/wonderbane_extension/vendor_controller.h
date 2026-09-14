#pragma once
#include "vendor_wire.h"
#include <map>
namespace wonderbane::extension::vendor {
class Invoker {
public:
    virtual ~Invoker() = default;
    // Submission is distinct from an unattempted stale request and an uncertain call.
    virtual wire::Outcome Invoke(wire::Verb, const wire::Snapshot&, std::uint32_t) noexcept = 0;
};
class Controller {
    struct Record { wire::Verb verb; wire::Command command; wire::Receipt receipt; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    Record* pending_ = nullptr;
    wire::Snapshot current_{};
    std::uint64_t revision_ = 0;
    bool uncertain_ = false;
    std::array<std::uint8_t, 16> transition_request_{};
    std::uint32_t transition_item_ = 0;
    static bool Contains(const wire::Snapshot& s, std::uint32_t item) noexcept {
        for (std::size_t i = 0; i < s.count; ++i) { if (s.slots[i].item == item) { return true; } }
        return false;
    }
    static bool SameOwner(const wire::Snapshot& a, const wire::Snapshot& b) noexcept {
        return a.scene == b.scene && a.root == b.root && a.manager == b.manager
            && a.menu == b.menu && a.hireling == b.hireling && a.building == b.building
            && a.vendor == b.vendor;
    }
    wire::Receipt Receipt(const wire::Command& command, wire::Outcome outcome, bool ready) const noexcept {
        wire::Receipt result{};
        result.request = command.request; result.host = command.host; result.window = command.window;
        result.snapshot = current_; result.outcome = static_cast<std::uint32_t>(outcome);
        result.flags = (ready && current_.scene && !uncertain_ && !pending_ ? wire::ready : 0)
            | (pending_ ? wire::in_flight : 0) | (uncertain_ ? wire::unresolved : 0);
        result.transition_request = transition_request_; result.transition_item = transition_item_;
        return result;
    }
public:
    const wire::Snapshot& Current() const noexcept { return current_; }
    std::uint32_t PendingKeep() const noexcept {
        return pending_ && pending_->verb == wire::Verb::keep ? pending_->command.item : 0;
    }
    // Called only on the owning thread, after fresh native ownership validation.
    // A displayed inventory item proves presence; its absence never proves failure.
    void Observe(wire::Snapshot snapshot, bool valid, bool kept_in_inventory) noexcept {
        snapshot.revision = current_.revision;
        if (!valid || !wire::Equal(snapshot, current_)) {
            if (revision_ == UINT64_MAX) { uncertain_ = true; current_ = {}; return; }
            snapshot.revision = ++revision_;
        }
        current_ = valid ? snapshot : wire::Snapshot{};
        if (!pending_ || uncertain_) { return; }
        const auto& before = pending_->command.expected;
        if (!valid || !SameOwner(before, current_) || current_.count < before.count) { uncertain_ = true; return; }
        std::uint32_t new_item = 0;
        if (pending_->verb == wire::Verb::create) {
            std::size_t additions = 0;
            for (std::size_t i = 0; i < before.count; ++i) {
                if (before.slots[i].item && !Contains(current_, before.slots[i].item)) {
                    uncertain_ = true; return;
                }
            }
            for (std::size_t i = 0; i < current_.count; ++i) {
                const auto item = current_.slots[i].item;
                if (item && !Contains(before, item)) { ++additions; new_item = item; }
            }
            if (additions > 1) { uncertain_ = true; return; }
            if (!additions) { return; }
        } else {
            if (Contains(current_, pending_->command.item) || !kept_in_inventory) { return; }
            new_item = pending_->command.item;
        }
        transition_item_ = new_item; transition_request_ = pending_->command.request; pending_ = nullptr;
    }
    wire::Receipt Execute(wire::Verb verb, const wire::Command& command,
        bool live, bool ready, Invoker& invoker) noexcept {
        using O = wire::Outcome;
        if (!wire::Valid(verb, command)) { return Receipt(command, O::invalid, ready); }
        if (!live) { return Receipt(command, O::stale, false); }
        if (verb == wire::Verb::inspect) { return Receipt(command, O::observed, ready); }
        const auto previous = records_.find(command.request);
        if (previous != records_.end()) {
            if (previous->second.verb != verb
                || std::memcmp(&previous->second.command, &command, sizeof(command))) {
                return Receipt(command, O::invalid, ready);
            }
            // Cached local submission, not a new invocation or server acceptance.
            return previous->second.receipt;
        }
        if (uncertain_) { return Receipt(command, O::uncertain, false); }
        if (pending_) { return Receipt(command, O::pending, false); }
        if (!ready || !wire::ValidSnapshot(current_)) { return Receipt(command, O::unavailable, false); }
        if (!wire::Equal(current_, command.expected)) { return Receipt(command, O::stale, ready); }
        bool eligible = false;
        for (std::size_t i = 0; i < current_.count; ++i) {
            const auto& slot = current_.slots[i];
            eligible |= verb == wire::Verb::create ? slot.state == 0
                : (slot.state == 2 && slot.item == command.item);
        }
        if (!eligible || (verb == wire::Verb::create && !wire::RandomScepter(current_))) {
            return Receipt(command, O::invalid, ready);
        }
        // Never evict action receipts and permit an old request to be replayed.
        // Exhaustion disables new actions until a fresh client process starts.
        if (records_.size() >= 4096) { return Receipt(command, O::exhausted, false); }
        try {
            auto [entry, inserted] = records_.emplace(command.request,
                Record{verb, command, Receipt(command, O::uncertain, false)});
            if (!inserted) { return Receipt(command, O::invalid, ready); }
            pending_ = &entry->second;
            const auto outcome = invoker.Invoke(verb, current_, command.item);
            if (outcome == O::stale || outcome == O::unavailable) { pending_ = nullptr; }
            else if (outcome != O::submitted) { uncertain_ = true; }
            entry->second.receipt = Receipt(command, outcome, false);
            return entry->second.receipt;
        } catch (...) { return Receipt(command, O::unavailable, false); }
    }
};
}
