#include "combat_v2_controller.h"
#undef NDEBUG
#include <cassert>
namespace c= wonderbane::extension::combat::v2;
namespace w=c::wire;
w::Id Id(unsigned value) {
    w::Id result{}; for(unsigned i=0;i<4;++i) { result[15-i]=static_cast<unsigned char>(value>>(i*8)); } return result;
}
w::Command Command(unsigned engagement,unsigned request,w::Action action=w::Action::attack) {
    w::Command result{}; result.host={1,1,1}; result.window=0x10000;
    result.grant.generation=1; result.grant.scene=1; result.grant.owner=1;
    strcpy_s(result.grant.token.worker,"worker"); strcpy_s(result.grant.token.operation,"operation");
    result.local_key[0]=100; result.local_key[1]=53; result.target_key[0]=200; result.target_key[1]=37;
    result.binding_digest.fill(1); result.request=Id(request); result.engagement=Id(engagement);
    result.action=action; result.power_id=action==w::Action::cast?428918601:0;
    return result;
}
struct Backend final:c::Invoker {
    unsigned binds{},submits{},stops{};
    bool defer_bind=false,defer_submit=false,fail_stop=false,retire_submit=false;
    c::Controller* controller{};
    unsigned reentrant{}; bool revoked=false, unknown_submit=false;
    void RevokeAdmission(const w::Command&) noexcept override { revoked=true; }
    c::Operation Bind(const w::Command& command) noexcept override {
        ++binds; revoked=false;
        if(reentrant==1) {
            auto control=command; control.action=w::Action::none; control.power_id=0;
            const auto pending=controller->Execute(w::Verb::stop,control,true,true,true,*this);
            assert(pending.phase==w::Phase::stopping && pending.flags&w::cleanup_required && revoked);
        }
        if(reentrant==4 || reentrant==5) {
            if(reentrant==5) { controller->Retire(command.grant.scene); }
            for(unsigned i=2;i<400;++i) {
                auto request=command; request.request=Id(i); request.action=w::Action::attack; request.power_id=0;
                if(reentrant==5) { request.engagement=Id(i+10); }
                (void)controller->Execute(w::Verb::cancel_action,request,true,true,true,*this);
            }
        }
        if(defer_bind) { return {w::Outcome::deferred,w::Entry::unknown,0,{}}; }
        return {w::Outcome::bound,w::Entry::unknown,0,{w::Phase::bound}};
    }
    c::Operation Submit(const w::Command& command) noexcept override {
        ++submits;
        if(reentrant==2 || reentrant==3) {
            auto request=command;
            if(reentrant==2) { request.action=w::Action::none; request.power_id=0; }
            const auto pending=controller->Execute(reentrant==2?w::Verb::stop:w::Verb::cancel_action,request,true,true,true,*this);
            assert(pending.phase==w::Phase::stopping && pending.flags&w::cleanup_required && revoked);
            if(reentrant==3) { assert(pending.entry==w::Entry::unknown && pending.outcome!=w::Outcome::action_cancelled); }
        }
        if(unknown_submit) { return {}; }
        if(retire_submit) { controller->Retire(command.grant.scene); }
        if(defer_submit) { return {w::Outcome::deferred,w::Entry::never_entered,0,{w::Phase::bound}}; }
        return {w::Outcome::client_outbound_queued,w::Entry::entered,w::outbound_queued,{w::Phase::bound}};
    }
    c::State Stop(const w::Command&) noexcept override {
        ++stops; return fail_stop?c::State{w::Phase::stopping}:c::State{w::Phase::closed,w::Closure::native_stopped,1,1,0};
    }
};
w::Receipt Execute(c::Controller& controller,Backend& backend,w::Verb verb,const w::Command& command,bool live=true,bool current=true) {
    const auto result=controller.Execute(verb,command,true,live,current,backend);
    assert(w::Correlated(command,verb,result)); return result;
}
int main() {
    c::Controller controller; Backend backend; backend.controller=&controller;
    auto control=Command(1,1,w::Action::none);
    auto result=Execute(controller,backend,w::Verb::bind,control);
    assert(result.outcome==w::Outcome::bound && backend.binds==1 && !backend.submits && !backend.stops);
    auto first=Command(1,1),second=Command(1,2,w::Action::cast);
    result=Execute(controller,backend,w::Verb::submit,first);
    assert(result.entry==w::Entry::entered && result.flags&w::outbound_queued);
    (void)Execute(controller,backend,w::Verb::submit,second);
    (void)Execute(controller,backend,w::Verb::submit,first);
    assert(backend.binds==1 && backend.submits==2 && !backend.stops);
    auto wrong=first; wrong.action=w::Action::cast; wrong.power_id=123;
    assert(Execute(controller,backend,w::Verb::submit,wrong).outcome==w::Outcome::invalid);
    backend.fail_stop=true; result=Execute(controller,backend,w::Verb::cancel_action,first,false,false);
    assert(result.phase==w::Phase::stopping && result.flags&w::cleanup_required && backend.stops==1);
    backend.fail_stop=false; result=Execute(controller,backend,w::Verb::stop,control,false,false);
    assert(result.phase==w::Phase::closed && result.closure==w::Closure::native_stopped);
    result=Execute(controller,backend,w::Verb::action_status,first,false,false);
    assert(result.outcome==w::Outcome::client_outbound_queued && result.flags&w::outbound_queued && result.phase==w::Phase::closed);
    assert(Execute(controller,backend,w::Verb::bind,control).phase==w::Phase::closed);
    assert(backend.binds==1 && backend.submits==2);
    // Unknown action cancellation reserves only that exact action, without input.
    auto cancel=Command(2,5);
    result=Execute(controller,backend,w::Verb::cancel_action,cancel);
    assert(result.outcome==w::Outcome::action_cancelled && result.phase==w::Phase::unknown && !result.flags);
    auto bind2=Command(2,1,w::Action::none); (void)Execute(controller,backend,w::Verb::bind,bind2);
    result=Execute(controller,backend,w::Verb::submit,cancel);
    assert(result.outcome==w::Outcome::action_cancelled && result.phase==w::Phase::bound && backend.submits==2);
    // Continuous actions exceed the old lifetime cap without re-entering evictions.
    for(unsigned i=6;i<=4200;++i) { (void)Execute(controller,backend,w::Verb::submit,Command(2,i)); }
    const auto submissions=backend.submits;
    result=Execute(controller,backend,w::Verb::submit,Command(2,6));
    assert(result.outcome==w::Outcome::history_expired && result.entry==w::Entry::unknown && !result.flags);
    assert(backend.submits==submissions);
    result=Execute(controller,backend,w::Verb::action_status,Command(2,4200));
    assert(result.outcome==w::Outcome::client_outbound_queued);
    // Future STOP cannot touch a different active owner, even after cache eviction.
    const auto stops=backend.stops;
    for(unsigned e=3;e<=400;++e) {
        result=Execute(controller,backend,w::Verb::stop,Command(e,1,w::Action::none));
        assert(result.closure==w::Closure::never_bound);
    }
    assert(backend.stops==stops);
    (void)Execute(controller,backend,w::Verb::submit,Command(2,4201));
    assert(backend.submits==submissions+1);
    result=Execute(controller,backend,w::Verb::bind,Command(3,1,w::Action::none));
    assert(result.outcome==w::Outcome::history_expired);
    (void)Execute(controller,backend,w::Verb::stop,bind2);
    // A newer actual owner permanently prevents an old unbound cache resurrecting.
    (void)Execute(controller,backend,w::Verb::cancel_action,Command(401,1));
    (void)Execute(controller,backend,w::Verb::bind,Command(402,1,w::Action::none));
    (void)Execute(controller,backend,w::Verb::stop,Command(402,2,w::Action::none));
    result=Execute(controller,backend,w::Verb::bind,Command(401,2,w::Action::none));
    assert(result.outcome==w::Outcome::history_expired);
    // No-input deferred binding is terminal and cannot turn replay into admission.
    backend.defer_bind=true;
    result=Execute(controller,backend,w::Verb::bind,Command(403,1,w::Action::none));
    assert(result.outcome==w::Outcome::deferred && result.entry==w::Entry::unknown && result.closure==w::Closure::never_bound);
    backend.defer_bind=false; const auto binds=backend.binds;
    result=Execute(controller,backend,w::Verb::bind,Command(403,1,w::Action::none));
    assert(result.outcome==w::Outcome::engagement_closed && backend.binds==binds);
    backend.retire_submit=true;
    result=Execute(controller,backend,w::Verb::submit,Command(404,1));
    assert(result.phase==w::Phase::retired && result.closure==w::Closure::scene_retired
        && result.entry==w::Entry::entered && result.flags&w::outbound_queued);
    for(unsigned kind=1;kind<=3;++kind) {
        c::Controller nested; Backend entered; entered.controller=&nested; entered.reentrant=kind;
        const auto command=Command(1,1,kind==1?w::Action::none:w::Action::cast);
        const auto stopped=Execute(nested,entered,kind==1?w::Verb::bind:w::Verb::submit,command);
        assert(stopped.phase==w::Phase::closed && stopped.closure==w::Closure::native_stopped && entered.stops==1);
        if(kind!=1) { assert(stopped.entry==w::Entry::entered && stopped.flags&w::outbound_queued); }
        assert(!nested.Busy());
        (void)Execute(nested,entered,kind==1?w::Verb::bind:w::Verb::submit,command);
        assert(entered.binds==1 && entered.submits==(kind==1?0U:1U));
    }
    for(unsigned pressure=4;pressure<=5;++pressure) {
        c::Controller nested; Backend entered; entered.controller=&nested;
        // Pin an earlier real closure so retirement need not pin the new record.
        (void)Execute(nested,entered,w::Verb::bind,Command(1,1,w::Action::none));
        (void)Execute(nested,entered,w::Verb::stop,Command(1,1,w::Action::none));
        entered.reentrant=pressure;
        const auto command=Command(2,1);
        const auto survived=Execute(nested,entered,w::Verb::submit,command);
        assert(survived.phase==(pressure==4?w::Phase::bound:w::Phase::retired));
        assert(entered.submits==(pressure==4?1U:0U));
        assert(Execute(nested,entered,w::Verb::action_status,command).phase==survived.phase);
    }
    {
        c::Controller owned; Backend entered; entered.controller=&owned;
        const auto command=Command(1,1);
        (void)Execute(owned,entered,w::Verb::submit,command);
        assert(owned.Update(command,{}));
        auto retained=Execute(owned,entered,w::Verb::engagement_status,Command(1,2,w::Action::none));
        assert(retained.phase==w::Phase::blocked && retained.flags&w::cleanup_required && owned.Busy());
        (void)Execute(owned,entered,w::Verb::stop,Command(1,3,w::Action::none));
        entered.unknown_submit=true;
        retained=Execute(owned,entered,w::Verb::submit,Command(2,1));
        assert(retained.phase==w::Phase::blocked && retained.flags&w::cleanup_required && owned.Busy());
        assert(entered.binds==2);
        (void)Execute(owned,entered,w::Verb::submit,Command(2,2));
        assert(entered.binds==2);
    }
    // Status never allocates a future ordinal or changes admission floors.
    backend.retire_submit=false;
    result=Execute(controller,backend,w::Verb::engagement_status,Command(9999,1,w::Action::none));
    assert(result.outcome==w::Outcome::history_expired);
    result=Execute(controller,backend,w::Verb::submit,Command(405,1));
    assert(result.outcome==w::Outcome::client_outbound_queued);
}
