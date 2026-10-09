#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <bit>
#include <cmath>
#include <span>

namespace wonderbane::extension::actor_actions {
using JournalDigest = std::array<std::uint8_t,32>;
// These records belong to the retained actor lifetime, not a Grant, target
// context, host policy object or replay cache. No timeout can remove them.
enum class ApplicationEntry { never_entered, entered, uncertain };
enum class ApplicationState { none, pending, observed, interrupted };
struct CoverageDeadline { std::uint32_t descriptor{}; std::uint64_t stamp{}; };
struct CoverageDeadlines {
    std::array<CoverageDeadline,64> values{};
    std::size_t count{};
    bool Add(std::uint32_t descriptor,std::uint64_t stamp) noexcept {
        const auto value=std::bit_cast<double>(stamp);
        if(!descriptor||!std::isfinite(value)||value<=0){return false;}
        for(std::size_t i=0;i<count;++i){if(values[i].descriptor==descriptor){
            if(stamp>values[i].stamp){values[i].stamp=stamp;}return true;
        }}
        if(count==values.size()){return false;}values[count++]={descriptor,stamp};return true;
    }
    std::span<const CoverageDeadline> View() const noexcept { return {values.data(),count}; }
};
struct ApplicationRecord {
    JournalDigest intent{}, command{};
    std::uint64_t submitted_revision{}, observed_revision{};
    ApplicationEntry entry = ApplicationEntry::never_entered;
    ApplicationState state = ApplicationState::none;
    bool reserved{}, local_settled{}, queued{};
    // Private bounded renewal baseline; every required descriptor must advance.
    CoverageDeadlines covered_deadlines{};
};
class ApplicationJournal final {
public:
    static constexpr std::size_t capacity = 32;
    static constexpr std::size_t invalid = capacity;
    // intent is the native-validated semantic coverage group digest (stable
    // across manifest ordering, Host, Grant and policy reconstruction). command
    // is the full immutable actor-action command digest, including request ID.
    std::size_t Reserve(const JournalDigest& intent,const JournalDigest& command,
                        std::uint64_t publication_revision,std::span<const CoverageDeadline> covered_deadlines={}) noexcept {
        CoverageDeadlines baseline{};
        for(const auto& value:covered_deadlines){if(!baseline.Add(value.descriptor,value.stamp)){return invalid;}}
        if (faulted_ || Zero(intent) || Zero(command) || !publication_revision) { return invalid; }
        for (const auto& record:records_) {
            if (record.reserved && (record.command==command
                || (record.intent==intent && (!record.local_settled
                    || record.state==ApplicationState::pending)))) { return invalid; }
        }
        for (std::size_t i=0;i<capacity;++i) {
            auto& record=records_[i];
            // A settled, observed effect needs no retained pending history. The
            // controller still owns immutable request replay/high-water history.
            if (!record.reserved || (record.local_settled && record.state!=ApplicationState::pending)) {
                record={intent,command,publication_revision,0,ApplicationEntry::never_entered,
                    ApplicationState::none,true,false,false,baseline};
                return i;
            }
        }
        return invalid; // Never evict a possible application to make room.
    }
    bool Record(std::size_t index,const JournalDigest& command,ApplicationEntry entry,
                bool queued,bool local_settled) noexcept {
        auto* record=Exact(index,command);
        if (!record || (entry!=ApplicationEntry::never_entered && entry!=ApplicationEntry::entered
                && entry!=ApplicationEntry::uncertain)
            || (queued && entry!=ApplicationEntry::entered)
            || (record->queued && !queued)
            || (record->entry==ApplicationEntry::entered && entry==ApplicationEntry::never_entered)
            || (record->entry==ApplicationEntry::uncertain && entry==ApplicationEntry::never_entered)
            || (record->local_settled && !local_settled)) {
            faulted_=true;return false;
        }
        if (record->entry!=ApplicationEntry::entered) { record->entry=entry; }
        record->queued |= queued;record->local_settled |= local_settled;
        if (entry!=ApplicationEntry::never_entered && record->state!=ApplicationState::observed
            && record->state!=ApplicationState::interrupted) {
            record->state=ApplicationState::pending;
        }
        return true;
    }
    // A positively observed interruption names one immutable queued command,
    // not the current group or an inferred server failure. The owning observer
    // supplies the exact activation generation. Local settlement is independent.
    bool Interrupt(std::size_t index,const JournalDigest& command,std::uint64_t submitted_revision,
                   std::uint64_t observation_revision) noexcept {
        auto* record=Exact(index,command);
        if(faulted_||!record||record->submitted_revision!=submitted_revision
            ||observation_revision<=submitted_revision||!record->queued
            ||record->entry!=ApplicationEntry::entered){return false;}
        if(record->state==ApplicationState::observed||record->state==ApplicationState::interrupted){return true;}
        if(record->state!=ApplicationState::pending){return false;}
        record->state=ApplicationState::interrupted;record->observed_revision=observation_revision;return true;
    }
    // Called only with fresh complete native coverage for this exact semantic
    // intent. Presence settles remote observation, never local responsibility.
    bool Observe(const JournalDigest& intent,std::uint64_t revision,bool complete,bool present,
                 std::span<const CoverageDeadline> deadlines={}) noexcept {
        if (faulted_ || Zero(intent) || !revision) { return false; }
        if (!complete || !present) { return true; }
        for (auto& record:records_) {
            if (record.reserved && record.intent==intent && record.state==ApplicationState::pending
                && revision>record.submitted_revision
                &&Advanced(record.covered_deadlines,deadlines)) {
                record.state=ApplicationState::observed;record.observed_revision=revision;
            }
        }
        return true;
    }
    bool Pending(const JournalDigest& intent) const noexcept {
        for (const auto& record:records_) {
            if (record.reserved && record.intent==intent
                && (!record.local_settled || record.state==ApplicationState::pending)) { return true; }
        }
        return false;
    }
    bool LocalPending() const noexcept {
        for (const auto& record:records_) { if (record.reserved && !record.local_settled) { return true; } }
        return false;
    }
    bool Faulted() const noexcept { return faulted_; }
    const auto& Records() const noexcept { return records_; }
    // No public clear/reset: the containing owner destroys this journal only
    // after its exact actor lifetime is retired. Parent/target closure keeps it.
private:
    static bool Advanced(const CoverageDeadlines& baseline,std::span<const CoverageDeadline> current) noexcept {
        for(const auto& old:baseline.View()){
            bool advanced=false;
            for(const auto& value:current){
                const auto deadline=std::bit_cast<double>(value.stamp);
                if(value.descriptor==old.descriptor&&std::isfinite(deadline)&&deadline>0&&value.stamp>old.stamp){advanced=true;break;}
            }
            if(!advanced){return false;}
        }
        return true;
    }
    static bool Zero(const JournalDigest& value) noexcept {
        for (auto byte:value) { if (byte) { return false; } }return true;
    }
    ApplicationRecord* Exact(std::size_t index,const JournalDigest& command) noexcept {
        return index<capacity && records_[index].reserved && records_[index].command==command
            ? &records_[index] : nullptr;
    }
    std::array<ApplicationRecord,capacity> records_{};
    bool faulted_{};
};
}
