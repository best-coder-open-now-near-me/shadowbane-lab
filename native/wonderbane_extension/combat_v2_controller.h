#pragma once
#include "combat_v2_wire.h"
#include <list>

namespace wonderbane::extension::combat::v2 {
struct State {
    wire::Phase phase = wire::Phase::unknown;
    wire::Closure closure = wire::Closure::none;
    std::uint32_t mode{}, action{}, target{};
};
struct Operation {
    wire::Outcome outcome = wire::Outcome::unavailable;
    wire::Entry entry = wire::Entry::unknown;
    std::uint32_t history{};
    State state{};
    std::array<char,73> detail{};
};
class Invoker {
public:
    virtual ~Invoker() = default;
    // Owner callback only; scalar/atomic latch, never native effects or locks.
    virtual void RevokeAdmission(const wire::Command&) noexcept = 0;
    virtual Operation Bind(const wire::Command&) noexcept = 0;
    virtual Operation Submit(const wire::Command&) noexcept = 0;
    virtual State Stop(const wire::Command&) noexcept = 0;
};
// One native owner-update thread. Positive big-endian ordinals allow bounded
// histories without ever turning eviction into permission for another entry.
class Controller final {
    using Id = wire::Id;
    using O = wire::Outcome;
    using P = wire::Phase;
    using C = wire::Closure;
    using E = wire::Entry;
    struct Engagement {
        wire::Command binding{};
        State state{};
        Id action_floor{};
        std::array<char,73> detail{};
        std::uint64_t update{};
        bool ever_bound = false, stop_requested = false;
        unsigned pins{};
    };
    struct Action {
        wire::Command command{};
        O outcome = O::uncertain;
        E entry = E::unknown;
        std::uint32_t history{};
        std::array<char,73> detail{};
        unsigned pins{};
    };
    template<class Record> struct Pin {
        Record* record{};
        explicit Pin(Record* value=nullptr) noexcept { Set(value); }
        ~Pin() { if(record) { --record->pins; } }
        void Set(Record* value) noexcept {
            if(record) { --record->pins; } record=value;
            if(record) { ++record->pins; }
        }
        Pin(const Pin&)=delete; Pin& operator=(const Pin&)=delete;
    };
    std::list<Engagement> engagements_;
    std::list<Action> actions_;
    Engagement* active_ = nullptr;
    Engagement* last_closed_ = nullptr;
    Action* in_flight_ = nullptr;
    wire::Command namespace_{};
    Id engagement_floor_{}, started_floor_{};
    bool namespace_set_ = false, calling_ = false;
    static constexpr std::size_t history_capacity = 256;

    static bool Owned(const State& s) noexcept {
        return s.phase == P::bound || s.phase == P::stopping || s.phase == P::blocked;
    }
    static bool Closed(const State& s) noexcept { return s.phase == P::closed || s.phase == P::retired; }
    static bool Valid(const State& s) noexcept {
        return s.phase <= P::blocked && s.target <= 1
            && ((s.phase == P::closed && (s.closure == C::never_bound || s.closure == C::native_stopped))
                || (s.phase == P::retired && s.closure == C::scene_retired)
                || (!Closed(s) && s.closure == C::none));
    }
    static bool Namespace(const wire::Command& a,const wire::Command& b) noexcept {
        return a.window == b.window && !std::memcmp(&a.host,&b.host,sizeof(a.host))
            && !std::memcmp(&a.grant,&b.grant,sizeof(a.grant));
    }
    Engagement* Find(const Id& id) noexcept {
        for(auto& record:engagements_) { if(record.binding.engagement==id) { return &record; } }
        return nullptr;
    }
    Action* Find(const Id& engagement,const Id& request) noexcept {
        for(auto& record:actions_) {
            if(record.command.engagement==engagement && record.command.request==request) { return &record; }
        }
        return nullptr;
    }
    static wire::Receipt Receipt(const wire::Command& command,wire::Verb verb,O outcome,
        const State& state={},E entry=E::unknown,std::uint32_t history=0) noexcept {
        auto result=wire::Reply(command,verb,outcome);
        result.phase=state.phase; result.closure=state.closure;
        result.mode=state.mode; result.action_state=state.action; result.combat_target_present=state.target;
        result.flags=(Owned(state)?wire::cleanup_required:0U);
        if(command.action!=wire::Action::none) {
            result.entry=entry; result.flags|=history&(wire::outbound_queued|wire::uncertain_history);
        }
        return result;
    }
    static wire::Receipt Expired(const wire::Command& command,wire::Verb verb) noexcept {
        auto result=wire::Reply(command,verb,O::history_expired); result.closure=C::history_expired; return result;
    }
    void Apply(Engagement& record,const State& state) noexcept {
        if(!Valid(state) || (record.ever_bound && state.closure==C::never_bound)
            || (state.phase==P::unknown && (record.ever_bound || Owned(record.state)))) {
            record.state={P::blocked}; active_=&record; return;
        }
        record.state=state;
        if(Closed(state)) { record.stop_requested=false; }
        if(Owned(state)) { active_=&record; record.ever_bound=true; }
        else if(active_==&record) { active_=nullptr; }
        if(Closed(state) && (record.ever_bound || (!last_closed_ && !active_))) { last_closed_=&record; }
    }
    void Prune() noexcept {
        for(bool owned_history : {true,false}) {
            std::size_t count{};
            for(const auto& action:actions_) {
                const bool belongs=active_ && action.command.engagement==active_->binding.engagement;
                if(belongs==owned_history) { ++count; }
            }
            while(count>history_capacity) {
                auto candidate=actions_.begin();
                for(;candidate!=actions_.end();++candidate) {
                    const bool belongs=active_ && candidate->command.engagement==active_->binding.engagement;
                    if(!candidate->pins && &*candidate!=in_flight_ && belongs==owned_history) { break; }
                }
                if(candidate==actions_.end()) { break; }
                actions_.erase(candidate); --count;
            }
        }
        // Active and most-recent closure have reserved slots beyond the cache.
        while(engagements_.size()>history_capacity+2) {
            auto candidate=engagements_.begin();
            while(candidate!=engagements_.end() && (candidate->pins || &*candidate==active_ || &*candidate==last_closed_)) { ++candidate; }
            if(candidate==engagements_.end()) { break; }
            const auto id=candidate->binding.engagement;
            actions_.remove_if([&](const Action& action) { return !action.pins && &action!=in_flight_ && action.command.engagement==id; });
            engagements_.erase(candidate);
        }
    }
    wire::Receipt ActionReply(const Action& action,const Engagement& engagement,wire::Verb verb) const noexcept {
        const auto outcome=(verb==wire::Verb::cancel_action && action.outcome==O::power_reuse_blocked)
            ? O::action_cancelled : action.outcome;
        return Receipt(action.command,verb,outcome,engagement.state,action.entry,action.history);
    }
    void StopRecord(Engagement& engagement,Invoker& invoker) noexcept {
        if(!Owned(engagement.state)) { return; }
        // Stop linearizes at the request even when a native callback is still
        // entered. The callback may add history, but cannot reopen admission.
        engagement.stop_requested=true;
        invoker.RevokeAdmission(engagement.binding);
        engagement.state.phase=P::stopping; engagement.state.closure=C::none;
        if(engagement.update!=UINT64_MAX) { ++engagement.update; }
        if(calling_) { return; }
        const auto before=engagement.update;
        engagement.stop_requested=false;
        calling_=true; const auto state=invoker.Stop(engagement.binding); calling_=false;
        if(before==engagement.update && !Closed(engagement.state)) { Apply(engagement,state); }
    }
    bool BindRecord(Engagement& engagement,const wire::Command& command,bool live,Invoker& invoker,O& outcome) noexcept {
        if(Owned(engagement.state)) { outcome=engagement.state.phase==P::bound?O::bound:O::pending; return engagement.state.phase==P::bound; }
        if(Closed(engagement.state)) { outcome=O::engagement_closed; return false; }
        if(active_ || calling_) { Apply(engagement,{P::closed,C::never_bound}); outcome=O::deferred; return false; }
        if(command.engagement<started_floor_) { outcome=O::history_expired; return false; }
        if(!live) { Apply(engagement,{P::closed,C::never_bound}); outcome=O::unavailable; return false; }
        const auto before=engagement.update;
        // Reserve cleanup responsibility before invoking any native owner callback.
        engagement.state={P::blocked}; active_=&engagement; calling_=true;
        const auto result=invoker.Bind(command); calling_=false; outcome=result.outcome;
        engagement.detail=result.detail;
        if(!std::memchr(engagement.detail.data(),0,engagement.detail.size())) { engagement.detail={}; }
        if(before==engagement.update && !Closed(engagement.state)) {
            if(result.state.phase==P::unknown) { Apply(engagement,{P::closed,C::never_bound}); }
            else { Apply(engagement,result.state); }
        }
        engagement.ever_bound |= Owned(result.state) || result.state.closure==C::native_stopped;
        if(engagement.stop_requested && !Closed(engagement.state)) { StopRecord(engagement,invoker); }
        if(engagement.ever_bound) {
            started_floor_=(std::max)(started_floor_,command.engagement);
            if(last_closed_!=&engagement) { last_closed_=nullptr; }
        }
        return engagement.state.phase==P::bound;
    }
public:
    bool Busy() const noexcept { return active_ || calling_; }
    const wire::Command* Active() const noexcept { return active_?&active_->binding:nullptr; }
    std::array<char,73> Diagnose(const wire::Command& command) const noexcept {
        for(const auto& action:actions_) {
            if(!std::memcmp(&action.command,&command,sizeof(command))) { return action.detail; }
        }
        for(const auto& engagement:engagements_) {
            if(!std::memcmp(&engagement.binding,&command,sizeof(command))) { return engagement.detail; }
        }
        return {};
    }
    wire::Receipt Execute(wire::Verb verb,const wire::Command& command,bool valid,
        bool live,bool namespace_current,Invoker& invoker) noexcept {
        if(!valid || !wire::Valid(command.action,command.power_id,verb)) { return wire::Reply(command,verb,O::invalid); }
        if(!namespace_set_ || !Namespace(namespace_,command)) {
            if(verb==wire::Verb::action_status || verb==wire::Verb::engagement_status || !namespace_current) {
                return Expired(command,verb);
            }
            if(Busy()) { return wire::Reply(command,verb,O::pending); }
            engagements_.clear(); actions_.clear(); active_=last_closed_=nullptr;
            engagement_floor_=started_floor_={}; namespace_=command; namespace_set_=true;
        }
        auto* engagement=Find(command.engagement);
        Pin<Engagement> engagement_pin(engagement);
        if(engagement && !wire::SameEngagement(engagement->binding,command)) { return wire::Reply(command,verb,O::invalid); }
        auto* action=Find(command.engagement,command.request);
        Pin<Action> action_pin(action);
        if(wire::ActionVerb(verb) && action) {
            if(std::memcmp(&action->command,&command,sizeof(command))) { return wire::Reply(command,verb,O::invalid); }
            if(!engagement) { return Expired(command,verb); }
            if(verb==wire::Verb::cancel_action && (action->entry==E::entered || action==in_flight_)) { StopRecord(*engagement,invoker); }
            return ActionReply(*action,*engagement,verb);
        }
        if(verb==wire::Verb::action_status) { return Expired(command,verb); }
        if(verb==wire::Verb::engagement_status) {
            if(!engagement) { return Expired(command,verb); }
            return Receipt(command,verb,Closed(engagement->state)?O::engagement_closed:O::observed,engagement->state);
        }
        if(!engagement) {
            if(command.engagement<=engagement_floor_) { return Expired(command,verb); }
            if(!namespace_current) { return wire::Reply(command,verb,O::stale); }
            engagement_floor_=command.engagement;
            try { engagements_.push_back({command}); engagement=&engagements_.back(); engagement_pin.Set(engagement); }
            catch(...) { return Expired(command,verb); }
        }
        if(verb==wire::Verb::stop) {
            if(engagement->state.phase==P::unknown) { Apply(*engagement,{P::closed,C::never_bound}); }
            else { StopRecord(*engagement,invoker); }
            const auto result=Receipt(command,verb,Closed(engagement->state)?O::engagement_closed:O::pending,engagement->state);
            Prune(); return result;
        }
        if(verb==wire::Verb::bind) {
            O outcome{};
            (void)BindRecord(*engagement,command,live,invoker,outcome);
            const auto result=outcome==O::history_expired?Expired(command,verb):Receipt(command,verb,outcome,engagement->state);
            Prune(); return result;
        }
        if(command.request<=engagement->action_floor) { return Expired(command,verb); }
        engagement->action_floor=command.request;
        try { actions_.push_back({command}); action=&actions_.back(); action_pin.Set(action); }
        catch(...) { Prune(); return Expired(command,verb); }
        action->entry=E::never_entered;
        if(verb==wire::Verb::cancel_action) { action->outcome=O::action_cancelled; }
        else {
            O admission{};
            if(!BindRecord(*engagement,command,live,invoker,admission)) {
                action->outcome=admission; action->detail=engagement->detail;
            }
            else if(!live || calling_) { action->outcome=live?O::pending:O::unavailable; }
            else {
                const auto before=engagement->update;
                action->entry=E::unknown; action->history=wire::uncertain_history;
                in_flight_=action; calling_=true;
                const auto result=invoker.Submit(command);
                calling_=false; in_flight_=nullptr;
                action->outcome=result.outcome; action->entry=result.entry;
                action->history=result.history&(wire::outbound_queued|wire::uncertain_history);
                action->detail=result.detail;
                if(!std::memchr(action->detail.data(),0,action->detail.size())) { action->detail={}; }
                if(before==engagement->update && !Closed(engagement->state)) { Apply(*engagement,result.state); }
                if(engagement->stop_requested && !Closed(engagement->state)) { StopRecord(*engagement,invoker); }
                auto reply=ActionReply(*action,*engagement,verb);
                if(!wire::Valid(reply)) {
                    action->outcome=O::uncertain; action->entry=E::unknown;
                    action->history=wire::uncertain_history;
                    if(!Closed(engagement->state)) { Apply(*engagement,{P::blocked}); }
                }
            }
        }
        const auto result=action->outcome==O::history_expired?Expired(command,verb):ActionReply(*action,*engagement,verb);
        Prune(); return result;
    }
    bool Update(const wire::Command& command,const State& state) noexcept {
        auto* record=Find(command.engagement);
        if(!record || !Namespace(namespace_,command) || !wire::SameEngagement(record->binding,command)
            || record!=active_ || record->update==UINT64_MAX) { return false; }
        ++record->update; Apply(*record,state); return true;
    }
    void Retire(std::uint64_t scene) noexcept {
        for(auto& record:engagements_) {
            if(record.binding.grant.scene!=scene || Closed(record.state)) { continue; }
            if(record.update!=UINT64_MAX) { ++record.update; }
            Apply(record,{P::retired,C::scene_retired});
        }
    }
};
}
