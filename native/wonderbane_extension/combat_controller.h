#pragma once
#include "combat_wire.h"
#include "combat_diagnostic.h"
#include <map>

namespace wonderbane::extension::combat {
// All calls run on the existing native owner update. The backend owns native
// references and the admission ticket until cleanup or exact scene retirement.
class Invoker {
public:
    virtual ~Invoker() = default;
    virtual wire::Receipt Start(const wire::Command&) noexcept = 0;
    virtual wire::Receipt Cancel(const wire::Command&) noexcept = 0;
    virtual Diagnostic Diagnose(const wire::Command&) const noexcept { return {}; }
};

class Controller final {
    struct Record { wire::Command command; wire::Receipt receipt; std::uint64_t update = 0; Diagnostic diagnostic{}; };
    std::map<std::array<std::uint8_t, 16>, Record> records_;
    Record* active_ = nullptr;
    bool calling_ = false;

    static bool Correlated(const wire::Command& command, const wire::Receipt& receipt) noexcept {
        const auto expected = wire::Reply(command, receipt.outcome);
        return wire::Valid(receipt) && receipt.request == expected.request
            && !std::memcmp(&receipt.host, &expected.host, sizeof(receipt.host))
            && receipt.window == expected.window
            && !std::memcmp(&receipt.grant, &expected.grant, sizeof(receipt.grant))
            && receipt.revision == expected.revision
            && !std::memcmp(receipt.local_key, expected.local_key, sizeof(receipt.local_key))
            && !std::memcmp(receipt.target_key, expected.target_key, sizeof(receipt.target_key))
            && receipt.binding_digest == expected.binding_digest;
    }
    void Accept(Record& record, const wire::Receipt& receipt) noexcept {
        const bool terminal = receipt.phase == wire::Phase::retired
            || (receipt.outcome == wire::Outcome::local_cancelled
                && (receipt.flags & wire::local_cancelled));
        if (!Correlated(record.command, receipt)
            || (!terminal && !(receipt.flags & wire::cleanup_required))) {
            // An entered backend with an invalid reply cannot free its owner.
            record.receipt = wire::Reply(record.command, wire::Outcome::uncertain);
            record.receipt.flags = wire::cleanup_required;
            record.receipt.phase = wire::Phase::blocked;
            active_ = &record;
            return;
        }
        record.receipt = receipt;
        if (receipt.flags & wire::cleanup_required) { active_ = &record; }
        else if (active_ == &record) { active_ = nullptr; }
    }
    static void PreserveEvidence(Record& record, const wire::Receipt& receipt) noexcept {
        // A reentrant cleanup/retirement wins state publication, but a later
        // correlated native return may still establish earlier outbound history.
        if (Correlated(record.command, receipt)) {
            record.receipt.flags |= receipt.flags & wire::outbound_queued;
        }
    }
public:
    Diagnostic Diagnose(const wire::Command& command) const noexcept {
        const auto found = records_.find(command.request);
        return found != records_.end() && !std::memcmp(&found->second.command, &command, sizeof(command))
            ? found->second.diagnostic : Diagnostic{};
    }
    bool Busy() const noexcept { return active_ || calling_; }
    const wire::Command* Active() const noexcept { return active_ ? &active_->command : nullptr; }

    wire::Receipt Execute(wire::Verb verb, const wire::Command& command,
                          bool valid, bool live, Invoker& invoker) noexcept {
        using O = wire::Outcome;
        if (!valid || (verb != wire::Verb::start && verb != wire::Verb::status && verb != wire::Verb::cancel)) {
            return wire::Reply(command, O::invalid);
        }
        auto previous = records_.find(command.request);
        if (previous != records_.end()) {
            auto& record = previous->second;
            if (std::memcmp(&record.command, &command, sizeof(command))) {
                return wire::Reply(command, O::invalid);
            }
            if (verb != wire::Verb::cancel || active_ != &record || calling_) { return record.receipt; }
            // Transport lease loss does not discard an exact old owner's cleanup.
            const auto before = record.update;
            calling_ = true;
            const auto result = invoker.Cancel(record.command);
            calling_ = false;
            if (record.update == before && record.receipt.phase != wire::Phase::retired) { Accept(record, result); }
            PreserveEvidence(record, result);
            return record.receipt;
        }
        if (verb == wire::Verb::status) { return wire::Reply(command, O::unavailable); }
        if (verb == wire::Verb::cancel) {
            // Ledger insertion precedes every native side effect. An unknown
            // identity has never entered; pin its cancellation before replying so
            // a delayed queued START cannot acquire authority afterward. This
            // does not inspect or stop any other encounter or movement owner.
            if (records_.size() >= 4096) { return wire::Reply(command, O::exhausted); }
            try {
                auto receipt = wire::Reply(command, O::local_cancelled);
                receipt.flags = wire::local_cancelled;
                const auto [entry, inserted] = records_.emplace(command.request, Record{command, receipt, 0, {Stage::no_entry, O::local_cancelled}});
                return inserted ? entry->second.receipt : wire::Reply(command, O::invalid);
            } catch (...) { return wire::Reply(command, O::exhausted); }
        }
        if (!live) { return wire::Reply(command, O::stale); }
        if (Busy()) { return wire::Reply(command, O::pending); }
        // Never evict identities: replay must not become a second native attack.
        if (records_.size() >= 4096) { return wire::Reply(command, O::exhausted); }
        try {
            auto [entry, inserted] = records_.emplace(command.request,
                Record{command, wire::Reply(command, O::uncertain)});
            if (!inserted) { return wire::Reply(command, O::invalid); }
            auto& record = entry->second;
            record.receipt.flags = wire::cleanup_required;
            record.receipt.phase = wire::Phase::blocked;
            active_ = &record; calling_ = true;
            const auto before = record.update;
            const auto result = invoker.Start(record.command);
            // Capture the original attempt even when reentrant cleanup won receipt publication.
            // Cancellation/retirement never overwrite this per-identity diagnostic.
            if (Correlated(record.command, result)) { record.diagnostic = invoker.Diagnose(record.command); }
            calling_ = false;
            if (record.update == before && record.receipt.phase != wire::Phase::retired) { Accept(record, result); }
            PreserveEvidence(record, result);
            return record.receipt;
        } catch (...) { return wire::Reply(command, O::exhausted); }
    }

    // Called after the existing owner stop pipeline or a fresh active observation.
    // Unrelated UUIDs and mismatched immutable bindings cannot alter an old owner.
    bool Update(const wire::Receipt& receipt) noexcept {
        const auto found = records_.find(receipt.request);
        if (found == records_.end() || !Correlated(found->second.command, receipt)) { return false; }
        if (active_ != &found->second) { return false; }
        if (found->second.update == UINT64_MAX) { return false; }
        ++found->second.update;
        Accept(found->second, receipt); return true;
    }

    // Only the movement lifetime observer may call this for an exact retired epoch.
    void Retire(std::uint64_t epoch) noexcept {
        if (!epoch) { return; }
        for (auto& [id, record] : records_) {
            (void)id;
            if (record.command.grant.scene != epoch) { continue; }
            if (record.update != UINT64_MAX) { ++record.update; }
            record.receipt.phase = wire::Phase::retired;
            record.receipt.outcome = wire::Outcome::observed;
            record.receipt.flags &= ~wire::cleanup_required;
            if (active_ == &record) { active_ = nullptr; }
        }
    }
};
}
