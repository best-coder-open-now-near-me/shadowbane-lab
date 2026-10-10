#pragma once
#include "actor_action_wire.h"
#include <list>

namespace wonderbane::extension::actor {
struct State {
    wire::Phase phase=wire::Phase::unknown;
    wire::Closure closure=wire::Closure::none;
    std::uint32_t mode{},action{},target{};
};
struct Operation {
    wire::Outcome outcome=wire::Outcome::unavailable;
    wire::Entry entry=wire::Entry::never_entered;
    wire::LocalSettlement local=wire::LocalSettlement::settled;
    wire::Application application=wire::Application::none;
    std::uint32_t history{};
    wire::Reason reason=wire::Reason::none;
    State state{};
    std::array<char,73> detail{};
};
class Invoker {
public:
    virtual ~Invoker()=default;
    virtual Operation Open(const wire::Command&) noexcept=0;
    virtual Operation Attach(const wire::Command&) noexcept=0;
    virtual Operation Submit(const wire::Command&) noexcept=0;
    // Revoke is scalar-only and linearizes before any cleanup callback.
    virtual void Revoke(const wire::Command&,bool owner) noexcept=0;
    virtual State Stop(const wire::Command&,bool owner) noexcept=0;
};
// Owner-thread ledger. Positive big-endian IDs provide high water marks after
// bounded history eviction; no missing receipt can authorize repeat native entry.
class Controller final {
    using Id=wire::Id; using O=wire::Outcome; using P=wire::Phase;
    using C=wire::Closure; using E=wire::Entry; using L=wire::LocalSettlement;
    struct Scope {
        wire::Command binding{}; State state{}; Id action_floor{},context_floor{};
        std::uint64_t revision{}; bool ever_bound{},stop_requested{};
    };
    struct Action {
        wire::Command command{}; Operation result{};
    };
    std::list<Scope> parents_,contexts_;
    std::list<Action> actions_;
    Scope *parent_{},*context_{};
    wire::Command namespace_{}; Id parent_floor_{};
    bool namespace_set_{},calling_{};
    static constexpr std::size_t capacity=256;
    static bool Namespace(const wire::Command& a,const wire::Command& b) noexcept {
        return a.window==b.window&&!std::memcmp(&a.host,&b.host,sizeof(a.host))
            &&!std::memcmp(&a.grant,&b.grant,sizeof(a.grant));
    }
    static bool Parent(const wire::Command& a,const wire::Command& b) noexcept {
        return Namespace(a,b)&&a.parent_id==b.parent_id&&a.parent_digest==b.parent_digest;
    }
    static bool Child(const wire::Command& a,const wire::Command& b) noexcept {
        return Parent(a,b)&&a.context_id==b.context_id&&a.context_digest==b.context_digest;
    }
    static bool Terminal(const State& s) noexcept {return wire::Closed(s.phase);}
    static bool Valid(const State& s) noexcept {
        return s.phase<=P::blocked&&s.target<=1
            &&((s.phase==P::closed&&(s.closure==C::never_bound||s.closure==C::native_stopped||s.closure==C::local_released))
                ||(s.phase==P::retired&&s.closure==C::scene_retired)
                ||(!Terminal(s)&&s.closure==C::none))
            &&(s.closure!=C::native_stopped||(s.mode==1&&!s.target));
    }
    Scope* ParentRecord(const Id& id) noexcept {for(auto& p:parents_){if(p.binding.parent_id==id){return &p;}}return nullptr;}
    Scope* ContextRecord(const wire::Command& c) noexcept {for(auto& x:contexts_){if(x.binding.parent_id==c.parent_id&&x.binding.context_id==c.context_id){return &x;}}return nullptr;}
    Action* ActionRecord(const wire::Command& c) noexcept {for(auto& a:actions_){if(a.command.parent_id==c.parent_id&&a.command.request==c.request){return &a;}}return nullptr;}
    static wire::Receipt Expired(const wire::Command& c,wire::Verb v) noexcept {
        auto r=wire::Reply(c,v,O::history_expired);r.closure=C::history_expired;return r;
    }
    wire::Receipt Reply(const wire::Command& c,wire::Verb v,O out,Scope* p=nullptr,Scope* x=nullptr,const Operation* a=nullptr) const noexcept {
        auto r=wire::Reply(c,v,out);
        if(p){r.owner_phase=p->state.phase;r.mode=p->state.mode;r.action_state=p->state.action;r.combat_target_present=p->state.target;}
        if(x){r.context_phase=x->state.phase;}
        if(p&&Terminal(p->state)){
            r.closure=p->state.closure;r.closure_scope=wire::ClosureScope::owner;
            if(x){r.context_phase=p->state.phase;}
        }else if(x&&Terminal(x->state)){
            r.closure=x->state.closure;r.closure_scope=wire::ClosureScope::context;
            // Closure is historical. The current parent may now own another
            // target, so expose the exact cleanup observation of this child.
            r.mode=x->state.mode;r.action_state=x->state.action;r.combat_target_present=x->state.target;
        }
        r.flags=(wire::Owned(r.owner_phase)?wire::owner_cleanup:0U)|(wire::Owned(r.context_phase)?wire::context_cleanup:0U);
        if(c.action!=wire::Action::none){
            r.entry=a?a->entry:E::never_entered;r.local_settlement=a?a->local:L::settled;
            if(a){r.flags|=a->history;r.application=a->application;r.reason=a->reason;}
            if(r.application==wire::Application::pending||r.application==wire::Application::unknown){r.flags|=wire::application_pending;}
        }
        return r;
    }
    void Apply(Scope& record,const State& supplied,bool owner) noexcept {
        if(Terminal(record.state)){return;}
        State state=supplied;
        if(!Valid(state)||(record.ever_bound&&state.closure==C::never_bound)
            ||(record.ever_bound&&state.phase==P::unknown)){state={P::blocked};}
        record.state=state;++record.revision;
        record.ever_bound|=wire::Owned(state.phase)||state.closure==C::native_stopped||state.closure==C::local_released;
        auto*& active=owner?parent_:context_;
        if(wire::Owned(state.phase)){active=&record;}else if(active==&record){active=nullptr;}
        if(Terminal(state)){
            record.stop_requested=false;
            for(auto& action:actions_){
                if(Parent(action.command,record.binding)&&(owner||Child(action.command,record.binding))){action.result.local=L::settled;}
            }
            if(owner){
                for(auto& child:contexts_){if(Parent(child.binding,record.binding)){
                    child.state=state;child.stop_requested=false;++child.revision;
                    if(context_==&child){context_=nullptr;}
                }}
            }
        }
    }
    void StopScope(Scope& record,bool owner,Invoker& invoker) noexcept {
        if(Terminal(record.state)){return;}
        if(record.state.phase==P::unknown){Apply(record,{P::closed,C::never_bound},owner);return;}
        record.stop_requested=true;record.state.phase=P::stopping;record.state.closure=C::none;++record.revision;
        invoker.Revoke(record.binding,owner);
        if(calling_){return;}
        const auto before=record.revision;
        calling_=true;const auto state=invoker.Stop(record.binding,owner);calling_=false;
        if(before==record.revision){Apply(record,state,owner);}
    }
    bool PendingLocal() const noexcept {
        for(const auto& a:actions_){if(a.result.local!=L::settled){return true;}}return false;
    }
    bool QueryAlongsidePendingPower() const noexcept {
        for(const auto& a:actions_){
            if(a.result.local==L::settled){continue;}
            if((a.command.action!=wire::Action::cast&&a.command.action!=wire::Action::self_power)
                ||a.result.entry!=E::entered||!(a.result.history&wire::outbound_queued)
                ||a.result.outcome!=O::queued){return false;}
        }return true;
    }
    void Prune() noexcept {
        if(calling_){return;}
        while(actions_.size()>=capacity){
            auto i=actions_.begin();while(i!=actions_.end()&&i->result.local!=L::settled){++i;}
            if(i==actions_.end()){break;}actions_.erase(i);
        }
        while(contexts_.size()>=capacity){
            auto i=contexts_.begin();while(i!=contexts_.end()&&(!Terminal(i->state)||&*i==context_)){++i;}
            if(i==contexts_.end()){break;}
            const auto binding=i->binding;
            actions_.remove_if([&](const Action& a){return Child(a.command,binding)&&a.result.local==L::settled;});
            contexts_.erase(i);
        }
        while(parents_.size()>=capacity){
            auto i=parents_.begin();while(i!=parents_.end()&&(!Terminal(i->state)||&*i==parent_)){++i;}
            if(i==parents_.end()){break;}
            const auto binding=i->binding;
            actions_.remove_if([&](const Action& a){return Parent(a.command,binding)&&a.result.local==L::settled;});
            contexts_.remove_if([&](const Scope& s){return Parent(s.binding,binding)&&Terminal(s.state);});parents_.erase(i);
        }
    }
    bool Record(Action& a,const Operation& incoming) noexcept {
        auto result=incoming;
        const auto& old=a.result;
        if(result.entry>E::entered||result.local>L::settled||result.application>wire::Application::interrupted
            ||result.history&~(wire::outbound_queued|wire::uncertain_history)
            ||(old.entry==E::entered&&result.entry!=E::entered)
            ||((old.history&wire::uncertain_history)&&result.entry==E::never_entered)
            ||((old.history&result.history)!=old.history)
            ||(old.local==L::settled&&result.local!=L::settled)
            ||((old.application==wire::Application::observed||old.application==wire::Application::interrupted)
                &&result.application!=old.application)
            ||!wire::Valid(Reply(a.command,wire::Verb::submit,result.outcome,
                ParentRecord(a.command.parent_id),wire::Any(a.command.context_id)?ContextRecord(a.command):nullptr,&result))){
            if(auto* p=ParentRecord(a.command.parent_id);p&&!Terminal(p->state)){p->state.phase=P::blocked;}
            return false;
        }
        a.result=result;return true;
    }
public:
    bool ContextAllowsEntry() const noexcept {
        return !context_||(context_->state.phase==P::bound&&!context_->stop_requested);
    }
    bool Busy() const noexcept {return parent_||context_||calling_||PendingLocal();}
    const wire::Command* ActiveOwner() const noexcept {return parent_?&parent_->binding:nullptr;}
    const wire::Command* ActiveContext() const noexcept {return context_?&context_->binding:nullptr;}
    std::array<char,73> Diagnose(const wire::Command& c) noexcept {
        // Numeric IDs can recur in a new producer namespace. Never attach an
        // older action's diagnostic to a different immutable command.
        const auto* a=ActionRecord(c);
        return a&&!std::memcmp(&a->command,&c,sizeof(c))?a->result.detail:std::array<char,73>{};
    }
    bool UpdateAction(const wire::Command& c,const Operation& result) noexcept {
        auto* a=ActionRecord(c);if(!a||std::memcmp(&a->command,&c,sizeof(c))){return false;}
        return Record(*a,result);
    }
    // Native journal projection only. Observed remote effects never discharge
    // local responsibility, and evicted command history is never reconstructed.
    bool ObserveApplication(const wire::Digest& digest,wire::Application terminal=wire::Application::observed) noexcept {
        if(terminal!=wire::Application::observed&&terminal!=wire::Application::interrupted){return false;}
        for(auto& action:actions_){
            wire::Digest exact{};
            if(!wire::HashCommand(action.command,exact)||exact!=digest){continue;}
            if(action.result.application==wire::Application::none){return false;}
            if(action.result.application==wire::Application::observed||action.result.application==wire::Application::interrupted){
                return action.result.application==terminal;
            }
            if(terminal==wire::Application::interrupted&&(action.result.entry!=E::entered||!(action.result.history&wire::outbound_queued))){return false;}
            action.result.application=terminal;return true;
        }return false;
    }
    bool UpdateScope(const wire::Command& c,const State& state,bool owner) noexcept {
        auto* s=owner?ParentRecord(c.parent_id):ContextRecord(c);
        if(!s||!(owner?Parent(s->binding,c):Child(s->binding,c))){return false;}
        Apply(*s,state,owner);return true;
    }
    wire::Receipt Execute(wire::Verb v,const wire::Command& c,bool valid,bool live,bool namespace_current,Invoker& invoker) noexcept {
        if(!valid||!wire::Valid(v,c)||wire::ReadVerb(v)){return wire::Reply(c,v,O::invalid);}
        if(!namespace_set_||!Namespace(namespace_,c)){
            if(!namespace_current||(v!=wire::Verb::open_owner&&v!=wire::Verb::stop_owner)||Busy()){return Expired(c,v);}
            parents_.clear();contexts_.clear();actions_.clear();parent_=context_=nullptr;
            parent_floor_={};namespace_=c;namespace_set_=true;
        }
        if(!calling_){Prune();}
        auto* p=ParentRecord(c.parent_id);auto* x=wire::Any(c.context_id)?ContextRecord(c):nullptr;
        if((p&&!Parent(p->binding,c))||(x&&!Child(x->binding,c))){return Reply(c,v,O::invalid,p,x);}
        if(calling_){
            if(v==wire::Verb::stop_owner&&p){StopScope(*p,true,invoker);}
            else if(v==wire::Verb::stop_context&&x){StopScope(*x,false,invoker);}
            else if(v==wire::Verb::cancel_action&&p){
                const auto* a=ActionRecord(c);
                if(a&&!std::memcmp(&a->command,&c,sizeof(c))&&a->result.entry!=E::never_entered){StopScope(x?*x:*p,!x,invoker);}
            }
            const auto* pending=wire::ActionVerb(v)?ActionRecord(c):nullptr;
            return Reply(c,v,O::pending,p,x,pending&&!std::memcmp(&pending->command,&c,sizeof(c))?&pending->result:nullptr);
        }
        if(wire::ActionVerb(v)){
            if(auto* a=ActionRecord(c)){
                if(std::memcmp(&a->command,&c,sizeof(c))){return Reply(c,v,O::invalid,p,x);}
                if(!p||(wire::Any(c.context_id)&&!x)){return Expired(c,v);}
                if(v==wire::Verb::cancel_action&&a->result.entry!=E::never_entered){StopScope(x?*x:*p,!x,invoker);}
                const auto out=v==wire::Verb::cancel_action&&(a->result.outcome==O::power_reuse_blocked||a->result.reason>=wire::Reason::target_occupied)?O::cancelled:a->result.outcome;
                auto copy=a->result;if(out==O::cancelled){copy.reason=wire::Reason::none;}
                return Reply(c,v,out,p,x,&copy);
            }
            if(v==wire::Verb::action_status){return Expired(c,v);}
        }
        if(!p){
            if((v!=wire::Verb::open_owner&&v!=wire::Verb::stop_owner)||c.parent_id<=parent_floor_||!namespace_current){return Expired(c,v);}
            parent_floor_=c.parent_id;
            try{parents_.push_back({c});p=&parents_.back();}catch(...){return Expired(c,v);}
        }
        if(v==wire::Verb::owner_status){return Reply(c,v,Terminal(p->state)?O::closed:O::observed,p);}
        if(v==wire::Verb::stop_owner){StopScope(*p,true,invoker);return Reply(c,v,Terminal(p->state)?O::closed:O::pending,p);}
        if(v==wire::Verb::open_owner){
            if(Terminal(p->state)){return Reply(c,v,O::closed,p);}
            if(wire::Owned(p->state.phase)){return Reply(c,v,p->state.phase==P::bound?O::bound:O::pending,p);}
            if(parent_||PendingLocal()||!live){Apply(*p,{P::closed,C::never_bound},true);return Reply(c,v,O::unavailable,p);}
            p->state={P::blocked};parent_=p;const auto before=p->revision;
            calling_=true;auto result=invoker.Open(c);calling_=false;
            if(before==p->revision){Apply(*p,result.state.phase==P::unknown?State{P::closed,C::never_bound}:result.state,true);}
            if(p->stop_requested){StopScope(*p,true,invoker);}
            return Reply(c,v,result.outcome,p);
        }
        if(Terminal(p->state)&&wire::Any(c.context_id)&&!x){return Expired(c,v);}
        if(wire::Any(c.context_id)&&!x){
            if((v!=wire::Verb::attach_context&&v!=wire::Verb::stop_context)||c.context_id<=p->context_floor||!namespace_current){return Expired(c,v);}
            p->context_floor=c.context_id;
            try{contexts_.push_back({c});x=&contexts_.back();}catch(...){return Expired(c,v);}
        }
        if(v==wire::Verb::context_status){return Reply(c,v,Terminal(x->state)?O::closed:O::observed,p,x);}
        if(v==wire::Verb::stop_context){StopScope(*x,false,invoker);return Reply(c,v,Terminal(x->state)?O::closed:O::pending,p,x);}
        if(v==wire::Verb::attach_context){
            if(Terminal(x->state)){return Reply(c,v,O::closed,p,x);}
            if(wire::Owned(x->state.phase)){return Reply(c,v,x->state.phase==P::bound?O::bound:O::pending,p,x);}
            if(context_||p!=parent_||p->state.phase!=P::bound||PendingLocal()||!live){Apply(*x,{P::closed,C::never_bound},false);return Reply(c,v,O::unavailable,p,x);}
            x->state={P::blocked};context_=x;const auto before=x->revision;
            calling_=true;const auto result=invoker.Attach(c);calling_=false;
            if(before==x->revision){Apply(*x,result.state.phase==P::unknown?State{P::closed,C::never_bound}:result.state,false);}
            if(x->stop_requested){StopScope(*x,false,invoker);}
            return Reply(c,v,result.outcome,p,x);
        }
        if(c.request<=p->action_floor){return Expired(c,v);}
        p->action_floor=c.request;
        if(actions_.size()>=capacity){return Reply(c,v,O::exhausted,p,x);}
        Action* action{};
        try{actions_.push_back({c});action=&actions_.back();}catch(...){return Reply(c,v,O::exhausted,p,x);}
        action->result.outcome=O::deferred;
        if(v==wire::Verb::cancel_action){action->result.outcome=O::cancelled;}
        else if(live&&p==parent_&&p->state.phase==P::bound&&(!x||(x==context_&&x->state.phase==P::bound))&&ContextAllowsEntry()&&(!PendingLocal()||((c.action==wire::Action::track&&QueryAlongsidePendingPower())||c.action==wire::Action::group_chat))){
            action->result.entry=E::unknown;action->result.local=L::pending;action->result.outcome=O::uncertain;
            calling_=true;auto result=invoker.Submit(c);calling_=false;
            if(Terminal(p->state)||(x&&Terminal(x->state))){result.local=L::settled;}
            if(!Record(*action,result)){p->state.phase=P::blocked;}
            // A native lifetime/owner callback may have settled the scope while
            // Submit was on the stack. It cannot reopen local responsibility.
            if(Terminal(p->state)||(x&&Terminal(x->state))){action->result.local=L::settled;}
            if(p->stop_requested){StopScope(*p,true,invoker);}else if(x&&x->stop_requested){StopScope(*x,false,invoker);}
        }
        return Reply(c,v,action->result.outcome,p,x,&action->result);
    }
};
}
