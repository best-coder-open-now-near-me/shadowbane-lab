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
    struct Record {
        wire::Verb verb; wire::Command command; wire::Receipt receipt;
        std::array<std::uint32_t, 16> accepted_items{};
        std::uint32_t accepted_count = 0;
    };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    Record* pending_ = nullptr;
    wire::Snapshot current_{};
    wire::RemainingCounts remaining_{};
    std::uint64_t revision_ = 0, random_deadline_ = 0;
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
    wire::Receipt Receipt(const wire::Command& command, wire::Outcome outcome, bool ready,
        bool orders = false) const noexcept {
        wire::Receipt result{};
        result.request = command.request; result.host = command.host; result.window = command.window;
        result.snapshot = current_; result.outcome = static_cast<std::uint32_t>(outcome);
        result.flags = (ready && current_.scene && !uncertain_ && !pending_ ? wire::ready : 0)
            | (pending_ ? wire::in_flight : 0) | (uncertain_ ? wire::unresolved : 0);
        result.transition_request = transition_request_; result.transition_item = transition_item_;
        if (orders) {
            result.signature = wire::orders_magic;
            for (std::size_t i = 0; i < current_.count; ++i) {
                if (remaining_[i] > UINT8_MAX) {
                    result.snapshot = {}; result.flags &= ~wire::ready;
                    if (outcome == wire::Outcome::observed) {
                        result.outcome = static_cast<std::uint32_t>(wire::Outcome::unavailable);
                    }
                    std::memset(result.reserved, 0, sizeof(result.reserved)); return result;
                }
                result.reserved[i] = static_cast<std::uint8_t>(remaining_[i]);
            }
        }
        return result;
    }
public:
    bool Busy() const noexcept { return pending_ || uncertain_; }
    const wire::Snapshot& Current() const noexcept { return current_; }
    std::uint32_t OrdersAccepted(const wire::Snapshot& snapshot, const wire::Command& command) const noexcept {
        std::uint32_t count = 0;
        for (const auto& [request, record] : records_) {
            (void)request;
            if (record.verb == wire::Verb::create_orders && SameOwner(snapshot, record.command.expected)
                && !std::memcmp(record.command.reserved, command.reserved, 16)) { count += record.accepted_count; }
        }
        return count;
    }
    bool OrderItemsOwned(const wire::Snapshot& snapshot, const wire::RemainingCounts& remaining,
        const wire::Command& command) const noexcept {
        if (snapshot.count > snapshot.slots.size() || !SameOwner(snapshot, command.expected)
            || movement::wire::Zero(command.reserved, 16)) { return false; }
        const auto budget = wire::Budget(command);
        const auto accepted = OrdersAccepted(snapshot, command);
        std::uint32_t free = 0;
        for (std::size_t i = 0; i < snapshot.count; ++i) { free += !snapshot.slots[i].item; }
        if (accepted >= budget.orders || (!accepted && budget.orders != free)) { return false; }
        for (const auto& [request, record] : records_) {
            (void)request;
            if (record.verb == wire::Verb::create_orders && SameOwner(snapshot, record.command.expected)
                && !std::memcmp(record.command.reserved, command.reserved, 16)
                && std::memcmp(record.command.reserved + 16, command.reserved + 16, 24)) { return false; }
        }
        for (std::size_t i = 0; i < snapshot.count; ++i) {
            if (remaining[i] > UINT8_MAX) { return false; }
            if (!snapshot.slots[i].item || remaining[i] <= 1) { continue; }
            bool owned = false;
            for (const auto& [request, record] : records_) {
                (void)request;
                if (record.verb != wire::Verb::create_orders
                    || std::memcmp(record.command.reserved, command.reserved, 16)
                    || !SameOwner(snapshot, record.command.expected)) { continue; }
                for (std::size_t j = 0; j < record.accepted_count; ++j) {
                    owned |= record.accepted_items[j] == snapshot.slots[i].item;
                }
            }
            if (!owned) { return false; }
        }
        return true;
    }
    std::uint32_t PendingKeep() const noexcept {
        return pending_ && pending_->verb == wire::Verb::keep ? pending_->command.item : 0;
    }
    // Called only on the owning thread, after fresh native ownership validation.
    // A displayed inventory item proves presence; its absence never proves failure.
    void Observe(wire::Snapshot snapshot, bool valid, bool kept_in_inventory, std::uint64_t now = 0,
        wire::RemainingCounts remaining = {}) noexcept {
        snapshot.revision = current_.revision;
        if (!valid || !wire::Equal(snapshot, current_) || remaining != remaining_) {
            if (revision_ == UINT64_MAX) { uncertain_ = true; current_ = {}; return; }
            snapshot.revision = ++revision_;
        }
        const auto previous = current_;
        current_ = valid ? snapshot : wire::Snapshot{};
        remaining_ = valid ? remaining : wire::RemainingCounts{};
        if (!pending_ || uncertain_) { return; }
        // The ordinary generalized Create may show a native rejection dialog.
        // Absence of a correlated addition becomes uncertainty, never a retry.
        if ((pending_->verb == wire::Verb::create_random || pending_->verb == wire::Verb::create_orders)
            && now > random_deadline_) { uncertain_ = true; return; }
        const auto& before = pending_->command.expected;
        if (!valid || !SameOwner(before, current_) || current_.count < before.count) { uncertain_ = true; return; }
        std::uint32_t new_item = 0;
        if (wire::IsCreate(pending_->verb)) {
            std::size_t additions = 0, expected = before.multiple ? 0 : 1;
            if (before.multiple) {
                for (std::size_t i = 0; i < before.count; ++i) {
                    if (!before.slots[i].state) { ++expected; }
                }
            }
            // Partial batch arrivals must remain present until the whole request completes.
            for (std::size_t i = 0; i < previous.count; ++i) {
                if (previous.slots[i].item && !Contains(current_, previous.slots[i].item)) {
                    uncertain_ = true; return;
                }
            }
            for (std::size_t i = 0; i < current_.count; ++i) {
                const auto item = current_.slots[i].item;
                if (item && !Contains(before, item)) {
                    if (pending_->verb == wire::Verb::create_orders
                        && remaining_[i] != before.quantity) { uncertain_ = true; return; }
                    ++additions; new_item = item;
                }
            }
            if (additions > expected) { uncertain_ = true; return; }
            if (additions < expected) { return; }
            if (pending_->verb == wire::Verb::create_orders) {
                for (std::size_t i = 0; i < current_.count; ++i) {
                    if (current_.slots[i].item && !Contains(before, current_.slots[i].item)) {
                        pending_->accepted_items[pending_->accepted_count++] = current_.slots[i].item;
                    }
                }
            }
            // transition_item represents one member; the correlated snapshot contains all additions.
        } else {
            if (Contains(current_, pending_->command.item) || !kept_in_inventory) { return; }
            new_item = pending_->command.item;
        }
        transition_item_ = new_item; transition_request_ = pending_->command.request; pending_ = nullptr;
    }
    wire::Receipt Execute(wire::Verb verb, const wire::Command& command,
        bool live, bool ready, Invoker& invoker, std::uint64_t now = 0) noexcept {
        using O = wire::Outcome;
        const bool orders = verb == wire::Verb::inspect_orders || verb == wire::Verb::create_orders;
        if (!wire::Valid(verb, command)) { return Receipt(command, O::invalid, ready, orders); }
        if (!live) { return Receipt(command, O::stale, false, orders); }
        if (wire::IsInspect(verb)) { return Receipt(command, O::observed, ready, orders); }
        const auto previous = records_.find(command.request);
        if (previous != records_.end()) {
            if (previous->second.verb != verb
                || std::memcmp(&previous->second.command, &command, sizeof(command))) {
                return Receipt(command, O::invalid, ready, orders);
            }
            // Cached local submission, not a new invocation or server acceptance.
            return previous->second.receipt;
        }
        if (uncertain_) { return Receipt(command, O::uncertain, false, orders); }
        if (pending_) { return Receipt(command, O::pending, false, orders); }
        if (!ready || !wire::ValidSnapshot(current_)) { return Receipt(command, O::unavailable, false, orders); }
        if (!wire::Equal(current_, command.expected)) { return Receipt(command, O::stale, ready, orders); }
        if (verb == wire::Verb::create_orders && !OrderItemsOwned(current_, remaining_, command)) {
            return Receipt(command, O::unavailable, ready, true);
        }
        bool eligible = false;
        for (std::size_t i = 0; i < current_.count; ++i) {
            const auto& slot = current_.slots[i];
            eligible |= wire::IsCreate(verb) ? slot.state == 0
                : (slot.state == 2 && slot.item == command.item);
        }
        if (!eligible || (verb == wire::Verb::create && !wire::RandomScepter(current_))
            || (verb == wire::Verb::create_random && !wire::RandomSingle(current_))
            || (verb == wire::Verb::create_orders && !wire::RandomOrder(current_))) {
            return Receipt(command, O::invalid, ready, orders);
        }
        // Never evict action receipts and permit an old request to be replayed.
        // Exhaustion disables new actions until a fresh client process starts.
        const bool timed_create = verb == wire::Verb::create_random || verb == wire::Verb::create_orders;
        if (records_.size() >= 4096 || (timed_create && now > UINT64_MAX - 5000)) {
            return Receipt(command, O::exhausted, false, orders);
        }
        try {
            auto [entry, inserted] = records_.emplace(command.request,
                Record{verb, command, Receipt(command, O::uncertain, false, orders)});
            if (!inserted) { return Receipt(command, O::invalid, ready, orders); }
            pending_ = &entry->second;
            if (timed_create) { random_deadline_ = now + 5000; }
            const auto outcome = invoker.Invoke(verb, current_, command.item);
            if (outcome == O::stale || outcome == O::unavailable) { pending_ = nullptr; }
            else if (outcome != O::submitted) { uncertain_ = true; }
            entry->second.receipt = Receipt(command, outcome, false, orders);
            return entry->second.receipt;
        } catch (...) { return Receipt(command, O::unavailable, false, orders); }
    }
};
}
