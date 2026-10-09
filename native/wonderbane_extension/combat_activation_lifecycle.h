#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace wonderbane::extension::combat::activation {
// Semantic local activity, not a transport nonce or server failure. The observer
// supplies sealed scene identity, qualified native call-through and coherent
// before/after copies; all methods run under its short state lock.
struct ActivationIdentity {
    std::uintptr_t actor{};
    std::array<std::uint32_t,2> key{};
    std::uint64_t scene{};
    bool operator==(const ActivationIdentity&) const = default;
    bool Valid() const noexcept { return actor&&key[0]&&key[1]==53&&scene; }
};
enum class ActivationPhase { unknown, awaiting_start, following_owned, setting_state, awaiting_append, appending, awaiting_start_return,
    active, moving, interrupted, completing_state, awaiting_first_removal, removing_first,
    awaiting_tail_removal, removing_tail, awaiting_process_return, completed };
enum class ActivationOrigin { item, self_power };
class ActivationHistory final {
public:
    static constexpr std::size_t capacity=32, invalid=capacity;
    struct Record {
        ActivationIdentity identity{};
        std::uint64_t ticket{};
        std::uint32_t power{};
        ActivationPhase phase=ActivationPhase::unknown;
        bool queued{},owned_followup{},local_relinquished{};
        ActivationOrigin origin=ActivationOrigin::item;
    };
    struct Transition {
        std::uint64_t mutation{},ticket{};
        std::size_t index=invalid;
        explicit operator bool() const noexcept { return mutation&&ticket&&index<capacity; }
    };
    struct ManualTransition {
        std::uint64_t mutation{};
        explicit operator bool() const noexcept { return mutation!=0; }
    };
    // slot is the retained application-journal slot, reused only when that
    // journal permits it. Tickets are never reset across parent/producer changes.
    std::uint64_t Arm(std::size_t slot,const ActivationIdentity& identity,std::uint32_t power,
        ActivationOrigin origin=ActivationOrigin::item) noexcept {
        if(slot>=capacity||!identity.Valid()||!power||(bound_.Valid()&&bound_!=identity)||!Advance()){return 0;}
        bound_=identity;
        InvalidateActive(identity.actor);
        records_[slot]={identity,mutation_,power,ActivationPhase::awaiting_start,false,false,false,origin};
        return mutation_;
    }
    void QueueResult(std::size_t slot,std::uint64_t ticket,bool queued) noexcept {
        auto* record=Exact(slot,ticket);if(!record){return;}
        record->queued|=queued;
        if(!record->queued){record->phase=ActivationPhase::unknown;}
    }
    void OwnedFollowup(std::size_t slot,std::uint64_t ticket,bool normal_exact_followup) noexcept {
        auto* record=Exact(slot,ticket);if(!record||record->origin!=ActivationOrigin::self_power){return;}
        record->owned_followup|=normal_exact_followup;
    }
    Transition BeginOwnedFollowup(std::size_t slot,std::uint64_t ticket) noexcept {
        auto* record=Exact(slot,ticket);
        if(!record||record->origin!=ActivationOrigin::self_power||!record->queued
            ||record->phase!=ActivationPhase::awaiting_start||!Advance()){return {};}
        InvalidateActive(record->identity.actor);record->phase=ActivationPhase::following_owned;
        current_={mutation_,ticket,slot};return current_;
    }
    bool OwnedFollowupReturned(const Transition& token,bool normal_exact,bool state6) noexcept {
        auto* record=Current(token,ActivationPhase::following_owned);if(!record){return false;}
        record->owned_followup|=normal_exact;
        record->phase=!normal_exact?ActivationPhase::unknown:state6?ActivationPhase::active:ActivationPhase::awaiting_start;
        return normal_exact;
    }
    bool LocalInterrupted(std::size_t slot,std::uint64_t ticket,const ActivationIdentity& identity) const noexcept {
        return Interrupted(slot,ticket,identity)&&records_[slot].origin==ActivationOrigin::self_power
            &&records_[slot].owned_followup;
    }
    bool LocalTerminal(std::size_t slot,std::uint64_t ticket,const ActivationIdentity& identity) const noexcept {
        if(slot>=capacity||!ticket){return false;}const auto& record=records_[slot];
        return record.ticket==ticket&&record.identity==identity&&record.queued&&record.owned_followup
            &&record.origin==ActivationOrigin::self_power&&(Terminal(record.phase)||record.local_relinquished);
    }
    bool ResetExactLifetime(const ActivationIdentity& expected) noexcept {
        if(bound_!=expected||!expected.Valid()||!Advance()){return false;}
        records_={};bound_={};current_={};manual_={};frame_=message_=definition_=thread_=0;return true;
    }
    // Observe *actual* unscoped ordinary item sending, including a nested send
    // while an owned Scope exists. It must always call native original through.
    // Any item may share the configured coverage; its stack key is not authority.
    void ForeignItemSend(std::uintptr_t actor) noexcept {
        if(!Relevant(actor)||!Advance()){return;}
        for(auto& record:records_){if(record.identity.actor==actor&&!Terminal(record.phase)){record.phase=ActivationPhase::unknown;}}
    }
    void ForeignPowerUse(std::uintptr_t actor) noexcept { ForeignItemSend(actor); }
    // Positive ordinary manual sending is not proof of an outcome. It only
    // starts a candidate for later relinquishing the shared control domain.
    // The queued application interpretation remains unknown/pending.
    void ManualSend(std::uintptr_t actor,std::uint32_t power) noexcept {
        if(!Relevant(actor)||!power){return;}
        ForeignPowerUse(actor);
        manual_={bound_,power,ActivationPhase::awaiting_start,mutation_,mutation_,0,0,0,0};
    }
    ManualTransition BeginManualStart(const ActivationIdentity& identity,std::uint32_t power,
        std::uintptr_t frame,std::uintptr_t message,std::uintptr_t definition,std::uint32_t thread) noexcept {
        if(!ManualCurrent(ActivationPhase::awaiting_start)){return {};}
        if(manual_.identity!=identity||manual_.power!=power||!frame||!message||!definition||!thread){
            OtherActivity(identity.actor);return {};}
        if(!Advance()){return {};}
        manual_.frame=frame;manual_.message=message;manual_.definition=definition;manual_.thread=thread;
        manual_.phase=ActivationPhase::setting_state;manual_.mutation=mutation_;return {mutation_};
    }
    bool ManualStateReturned(ManualTransition token,bool coherent_state6) noexcept {
        if(token.mutation!=mutation_||!ManualCurrent(ActivationPhase::setting_state)){return false;}
        manual_.phase=coherent_state6?ActivationPhase::awaiting_append:ActivationPhase::unknown;return coherent_state6;
    }
    ManualTransition BeginManualAppend(const ActivationIdentity& identity,std::uint32_t power,
        std::uintptr_t frame,std::uintptr_t message,std::uintptr_t definition,std::uint32_t thread) noexcept {
        if(!ManualCurrent(ActivationPhase::awaiting_append)||manual_.identity!=identity||manual_.power!=power
            ||manual_.frame!=frame||manual_.message!=message||manual_.definition!=definition||manual_.thread!=thread){
            OtherActivity(identity.actor);return {};}
        if(!Advance()){return {};}
        manual_.phase=ActivationPhase::appending;manual_.mutation=mutation_;return {mutation_};
    }
    bool ManualAppendReturned(ManualTransition token,bool coherent_append) noexcept {
        if(token.mutation!=mutation_||!ManualCurrent(ActivationPhase::appending)){return false;}
        manual_.phase=coherent_append?ActivationPhase::awaiting_start_return:ActivationPhase::unknown;return coherent_append;
    }
    bool ManualProcessReturned(ManualTransition token,bool normal_exact_return) noexcept {
        if(token.mutation!=mutation_||!ManualCurrent(ActivationPhase::awaiting_start_return)){return false;}
        manual_.phase=ActivationPhase::unknown;
        if(!normal_exact_return){return false;}
        RelinquishManual();
        return true;
    }
    bool ManualDirectReturned(const ActivationIdentity& identity,std::uint32_t power,bool coherent) noexcept {
        if(!coherent||!ManualCurrent(ActivationPhase::awaiting_start)||manual_.identity!=identity||manual_.power!=power){return false;}
        manual_.phase=ActivationPhase::unknown;RelinquishManual();return true;
    }
    void OtherActivity(std::uintptr_t actor) noexcept {
        if(!Relevant(actor)||!Advance()){return;}InvalidateActive(actor);
    }
    Transition BeginStart(const ActivationIdentity& identity,std::uint32_t power,
        std::uintptr_t process_frame,std::uintptr_t message,std::uintptr_t definition,std::uint32_t thread) noexcept {
        if(!Relevant(identity.actor)||!Advance()){return {};}
        std::size_t found=invalid;bool ambiguous=false;
        for(std::size_t i=0;i<capacity;++i){auto& record=records_[i];
            const bool direct=record.phase==ActivationPhase::active&&record.origin==ActivationOrigin::self_power
                &&record.owned_followup&&current_.index==i&&current_.ticket==record.ticket
                &&current_.mutation+1==mutation_;
            if(record.identity==identity&&record.power==power&&(record.phase==ActivationPhase::awaiting_start||direct)){
                if(!record.queued){record.phase=ActivationPhase::unknown;continue;}
                if(found!=invalid){ambiguous=true;}
                found=i;
            }
        }
        InvalidateActive(identity.actor);
        if(ambiguous){
            for(auto& record:records_){if(record.identity==identity&&record.power==power&&!Terminal(record.phase)){
                record.phase=ActivationPhase::unknown;}}
            return {};
        }
        if(found==invalid||!process_frame||!message||!definition||!thread){return {};}
        frame_=process_frame;message_=message;definition_=definition;thread_=thread;
        auto& record=records_[found];record.phase=ActivationPhase::setting_state;
        current_={mutation_,record.ticket,found};return current_;
    }
    bool StateReturned(const Transition& token,bool coherent_state6) noexcept {
        auto* record=Current(token,ActivationPhase::setting_state);
        if(!record){return false;}
        record->phase=coherent_state6?ActivationPhase::awaiting_append:ActivationPhase::unknown;
        return coherent_state6;
    }
    Transition BeginAppend(const ActivationIdentity& identity,std::uint32_t power,
        std::uintptr_t frame,std::uintptr_t message,std::uintptr_t definition,std::uint32_t thread) noexcept {
        auto* record=Current(current_,ActivationPhase::awaiting_append);
        const bool exact=record&&record->identity==identity&&record->power==power
            &&frame_==frame&&message_==message&&definition_==definition&&thread_==thread;
        if(!exact){OtherActivity(identity.actor);return {};}
        if(!Advance()){return {};}
        record->phase=ActivationPhase::appending;current_.mutation=mutation_;return current_;
    }
    bool AppendReturned(const Transition& token,bool coherent_appended_one) noexcept {
        auto* record=Current(token,ActivationPhase::appending);if(!record){return false;}
        // Prefix-preserving N -> N+1 append, including duplicate IDs and native
        // vector relocation, is qualified by the caller. No uniqueness rule.
        record->phase=coherent_appended_one?ActivationPhase::awaiting_start_return:ActivationPhase::unknown;
        return coherent_appended_one;
    }
    bool StartProcessReturned(const Transition& token,bool normal_exact_return) noexcept {
        auto* record=Current(token,ActivationPhase::awaiting_start_return);if(!record){return false;}
        record->phase=normal_exact_return?ActivationPhase::active:ActivationPhase::unknown;return normal_exact_return;
    }
    Transition BeginMovement(const ActivationIdentity& identity) noexcept {
        auto* record=Current(current_,ActivationPhase::active);
        const bool exact=record&&record->identity==identity;
        if(!exact){OtherActivity(identity.actor);return {};}
        if(!Advance()){return {};}
        record->phase=ActivationPhase::moving;current_.mutation=mutation_;return current_;
    }
    bool MovementReturned(const Transition& token,bool coherent_state6_to7) noexcept {
        auto* record=Current(token,ActivationPhase::moving);if(!record){return false;}
        record->phase=coherent_state6_to7?ActivationPhase::interrupted:ActivationPhase::unknown;
        return coherent_state6_to7;
    }
    // The exact successful incoming completion path observes state 6 -> 5,
    // then both the first and common-tail removers in the same Process frame.
    // Retained duplicate IDs are bookkeeping; terminal generation, not vector
    // emptiness, establishes the old local responsibility's end.
    Transition BeginCompletion(const ActivationIdentity& identity,std::uint32_t power,
        std::uintptr_t frame,std::uintptr_t message,std::uintptr_t definition,std::uint32_t thread) noexcept {
        auto* record=Current(current_,ActivationPhase::active);
        if(!record||record->identity!=identity||record->power!=power||!frame||!message||!definition||!thread){
            OtherActivity(identity.actor);return {};
        }
        if(!Advance()){return {};}
        frame_=frame;message_=message;definition_=definition;thread_=thread;
        record->phase=ActivationPhase::completing_state;current_.mutation=mutation_;return current_;
    }
    bool CompletionStateReturned(const Transition& token,bool coherent_state6_to5) noexcept {
        auto* record=Current(token,ActivationPhase::completing_state);if(!record){return false;}
        record->phase=coherent_state6_to5?ActivationPhase::awaiting_first_removal:ActivationPhase::unknown;
        return coherent_state6_to5;
    }
    Transition BeginRemoval(const ActivationIdentity& identity,std::uint32_t power,
        std::uintptr_t frame,std::uintptr_t message,std::uintptr_t definition,std::uint32_t thread,bool final) noexcept {
        auto* record=Current(current_,final?ActivationPhase::awaiting_tail_removal:ActivationPhase::awaiting_first_removal);
        if(!record||record->identity!=identity||record->power!=power||frame_!=frame||message_!=message
            ||definition_!=definition||thread_!=thread){OtherActivity(identity.actor);return {};}
        if(!Advance()){return {};}
        record->phase=final?ActivationPhase::removing_tail:ActivationPhase::removing_first;
        current_.mutation=mutation_;return current_;
    }
    bool RemovalReturned(const Transition& token,bool final,bool coherent_removal) noexcept {
        auto* record=Current(token,final?ActivationPhase::removing_tail:ActivationPhase::removing_first);
        if(!record){return false;}
        record->phase=!coherent_removal?ActivationPhase::unknown:
            final?ActivationPhase::awaiting_process_return:ActivationPhase::awaiting_tail_removal;
        return coherent_removal;
    }
    bool CompletionProcessReturned(const Transition& token,bool normal_exact_return) noexcept {
        auto* record=Current(token,ActivationPhase::awaiting_process_return);if(!record){return false;}
        record->phase=normal_exact_return?ActivationPhase::completed:ActivationPhase::unknown;return normal_exact_return;
    }
    bool Interrupted(std::size_t slot,std::uint64_t ticket,const ActivationIdentity& identity) const noexcept {
        if(slot>=capacity||!ticket){return false;}const auto& record=records_[slot];
        return record.ticket==ticket&&record.identity==identity&&record.queued&&record.phase==ActivationPhase::interrupted;
    }
    Record Read(std::size_t slot) const noexcept { return slot<capacity?records_[slot]:Record{}; }
    std::uint64_t Mutation() const noexcept { return mutation_; }
private:
    struct Manual {
        ActivationIdentity identity{};
        std::uint32_t power{};
        ActivationPhase phase=ActivationPhase::unknown;
        std::uint64_t mutation{},send_mutation{};
        std::uintptr_t frame{},message{},definition{};
        std::uint32_t thread{};
    } manual_{};
    bool ManualCurrent(ActivationPhase phase) const noexcept {
        return manual_.mutation&&manual_.mutation==mutation_&&manual_.phase==phase;
    }
    void RelinquishManual() noexcept {
        for(auto& record:records_){
            if(record.identity==manual_.identity&&record.ticket<manual_.send_mutation&&record.queued
                &&record.owned_followup&&record.origin==ActivationOrigin::self_power&&!Terminal(record.phase)){record.local_relinquished=true;}
        }
    }
    static bool Terminal(ActivationPhase phase) noexcept {
        return phase==ActivationPhase::interrupted||phase==ActivationPhase::completed;
    }
    bool Relevant(std::uintptr_t actor) const noexcept {
        return bound_.Valid()&&bound_.actor==actor;
    }
    bool Advance() noexcept {
        if(mutation_==std::numeric_limits<std::uint64_t>::max()){
            for(auto& record:records_){record.phase=ActivationPhase::unknown;}return false;
        }
        ++mutation_;return true;
    }
    void InvalidateActive(std::uintptr_t actor) noexcept {
        for(auto& record:records_){if(record.identity.actor==actor
            &&record.phase!=ActivationPhase::awaiting_start&&!Terminal(record.phase)){record.phase=ActivationPhase::unknown;}}
    }
    Record* Exact(std::size_t slot,std::uint64_t ticket) noexcept {
        return slot<capacity&&ticket&&records_[slot].ticket==ticket?&records_[slot]:nullptr;
    }
    Record* Current(const Transition& token,ActivationPhase phase) noexcept {
        auto* record=Exact(token.index,token.ticket);
        return token.mutation==mutation_&&record&&record->phase==phase?record:nullptr;
    }
    std::array<Record,capacity> records_{};
    // One history belongs to one exact actor lifetime, like ApplicationJournal.
    // Its owner replaces it only after positive native scene retirement.
    ActivationIdentity bound_{};
    std::uint64_t mutation_{};
    Transition current_{};
    std::uintptr_t frame_{},message_{},definition_{};
    std::uint32_t thread_{};
};
}
