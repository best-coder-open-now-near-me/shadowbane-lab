#include "actor_action_controller.h"
#include <cstdio>
#include <fstream>
#include <string>
namespace a=wonderbane::extension::actor;
namespace w=a::wire;
namespace {
unsigned failures{},checks{};
void Check(bool ok,const char* label){++checks;if(!ok){++failures;std::fprintf(stderr,"%s\n",label);}}
w::Id Id(unsigned n){w::Id id{};for(unsigned i=0;i<4;++i){id[15-i]=static_cast<std::uint8_t>(n>>(i*8));}return id;}
int Hex(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;}
template<class T> bool Read(const char* path,T& out){std::ifstream f(path);std::string s;f>>s;if(s.size()!=sizeof(T)*2){return false;}auto* b=reinterpret_cast<unsigned char*>(&out);for(std::size_t i=0;i<sizeof(T);++i){const int x=Hex(s[i*2]),y=Hex(s[i*2+1]);if(x<0||y<0){return false;}b[i]=static_cast<unsigned char>((x<<4)|y);}return true;}
w::Command Plain(w::Command c){c.action=w::Action::none;c.power_id=0;c.item_key[0]=c.item_key[1]=c.template_key[0]=c.template_key[1]=0;c.item_hint=c.template_hint=0;c.recipient=w::Recipient::none;c.selector_index=w::no_selector;c.manifest_digest={};c.publication_revision=0;c.snapshot_id={};return c;}
struct Fake final:a::Invoker {
    unsigned opens{},attaches{},submits{},stops{},revokes{};
    bool local_pending{},stop_pending{},reuse{},reenter{},unknown_entry{};
    w::Reason admission_reason=w::Reason::none;
    a::Controller* controller{};
    a::Operation Open(const w::Command&) noexcept override {++opens;a::Operation r;r.outcome=w::Outcome::bound;r.state.phase=w::Phase::bound;return r;}
    a::Operation Attach(const w::Command&) noexcept override {++attaches;a::Operation r;r.outcome=w::Outcome::bound;r.state.phase=w::Phase::bound;return r;}
    a::Operation Submit(const w::Command& c) noexcept override {
        ++submits;a::Operation r;r.state.phase=w::Phase::bound;
        if(admission_reason!=w::Reason::none){r.outcome=w::Outcome::deferred;r.reason=admission_reason;return r;}
        if(reuse){r.outcome=w::Outcome::power_reuse_blocked;r.reason=w::Reason::power_reuse;return r;}
        r.outcome=w::Outcome::queued;r.entry=w::Entry::entered;r.history=w::outbound_queued;
        r.local=local_pending&&c.action!=w::Action::track?w::LocalSettlement::pending:w::LocalSettlement::settled;
        r.application=(c.action==w::Action::attack||c.action==w::Action::track)?w::Application::none:w::Application::pending;
        if(unknown_entry){r.outcome=w::Outcome::uncertain;r.entry=w::Entry::unknown;
            r.history=w::uncertain_history;r.local=w::LocalSettlement::pending;r.application=w::Application::unknown;}
        if(reenter){auto stop=Plain(c);stop.context_id={};stop.context_digest={};(void)controller->Execute(w::Verb::stop_owner,stop,true,true,true,*this);}
        return r;
    }
    void Revoke(const w::Command&,bool) noexcept override {++revokes;}
    a::State Stop(const w::Command&,bool) noexcept override {++stops;return stop_pending?a::State{w::Phase::stopping}:a::State{w::Phase::closed,w::Closure::native_stopped,1,1,0};}
};
w::Receipt Run(a::Controller& c,Fake& f,w::Verb v,const w::Command& cmd,bool live=true,bool current=true){
    Check(w::Valid(v,cmd),"input wire valid");const auto r=c.Execute(v,cmd,true,live,current,f);
    Check(w::Correlated(cmd,v,r),"output wire valid and exact correlated");return r;
}
}
int main(int argc,char** argv){
    if(argc!=3){return 2;}w::Command item{};a::fence::ContextBinding child{};
    if(!Read(argv[1],item)||!Read(argv[2],child)){return 2;}
    auto owner=Plain(item);owner.request=Id(1);
    auto context=owner;context.context_id=child.context_id;Check(a::fence::HashBinding(child,context.context_digest),"context hash");
    auto attack=context;attack.request=Id(10);attack.action=w::Action::attack;attack.recipient=w::Recipient::target;
    item.request=Id(11);
    {
        a::Controller query_controller;Fake query_native;query_native.controller=&query_controller;
        Run(query_controller,query_native,w::Verb::open_owner,owner);
        Run(query_controller,query_native,w::Verb::attach_context,context);
        auto casting=Plain(attack);casting.action=w::Action::cast;casting.power_id=111;
        casting.recipient=w::Recipient::target;casting.request=Id(2);
        query_native.local_pending=true;
        const auto original=Run(query_controller,query_native,w::Verb::submit,casting);
        Check(original.local_settlement==w::LocalSettlement::pending,"normal power remains locally pending");
        auto query=owner;query.request=Id(3);query.action=w::Action::track;
        query.power_id=429578587;query.recipient=w::Recipient::actor;
        const auto receipt=Run(query_controller,query_native,w::Verb::submit,query);
        Check(receipt.outcome==w::Outcome::queued&&receipt.application==w::Application::none
            &&receipt.local_settlement==w::LocalSettlement::settled&&query_native.submits==2,
            "query can run beside queued power without owning its child");
        Run(query_controller,query_native,w::Verb::action_status,query);
        const auto retained=Run(query_controller,query_native,w::Verb::action_status,casting);
        Check(retained.local_settlement==w::LocalSettlement::pending&&retained.command_digest==original.command_digest,
            "query status preserves original cast obligation");
        Check(!w::Valid(w::Verb::cancel_action,query),"query cannot cancel owner combat");

        query_native.stop_pending=true;Run(query_controller,query_native,w::Verb::stop_context,context);
        query.request=Id(5);
        Check(Run(query_controller,query_native,w::Verb::submit,query).entry==w::Entry::never_entered,
            "query never bypasses exact child cleanup");
    }
    {
        a::Controller unknown;Fake backend;backend.controller=&unknown;
        Run(unknown,backend,w::Verb::open_owner,owner);Run(unknown,backend,w::Verb::attach_context,context);
        auto casting=Plain(attack);casting.action=w::Action::cast;casting.power_id=111;
        casting.recipient=w::Recipient::target;casting.request=Id(2);backend.unknown_entry=true;
        Check(Run(unknown,backend,w::Verb::submit,casting).entry==w::Entry::unknown,"unknown native entry retained");
        auto query=owner;query.request=Id(3);query.action=w::Action::track;query.power_id=429578587;
        query.recipient=w::Recipient::actor;const auto calls=backend.submits;
        Check(Run(unknown,backend,w::Verb::submit,query).entry==w::Entry::never_entered&&backend.submits==calls,
            "tracking cannot bypass unknown native responsibility");
    }
    a::Controller c;Fake f;f.controller=&c;
    Check(Run(c,f,w::Verb::open_owner,owner).outcome==w::Outcome::bound&&f.opens==1,"open one actor owner");
    Run(c,f,w::Verb::open_owner,owner);Check(f.opens==1,"repeated owner does not bind twice");
    Check(Run(c,f,w::Verb::attach_context,context).outcome==w::Outcome::bound,"attach child");
    const auto hit=Run(c,f,w::Verb::submit,attack);Check(hit.entry==w::Entry::entered&&f.submits==1,"attack entered once");
    Run(c,f,w::Verb::submit,attack);Check(f.submits==1,"immutable replay never reenters");
    auto changed=attack;changed.context_digest[0]^=1;
    Check(Run(c,f,w::Verb::submit,changed).outcome==w::Outcome::invalid&&f.submits==1,"changed authority cannot reuse action identity");
    const auto potion=Run(c,f,w::Verb::submit,item);
    Check(potion.application==w::Application::pending&&potion.local_settlement==w::LocalSettlement::settled,"remote potion pending independent of local entry");
    const auto closed=Run(c,f,w::Verb::stop_context,context);
    Check(closed.owner_phase==w::Phase::bound&&closed.context_phase==w::Phase::closed&&closed.flags==w::owner_cleanup,"child cleanup retains parent");
    const auto retained=Run(c,f,w::Verb::action_status,item);
    Check(retained.application==w::Application::pending&&retained.owner_phase==w::Phase::bound,"child stop retains actor application history");
    w::Digest item_digest{};Check(w::HashCommand(item,item_digest)
        &&c.ObserveApplication(item_digest,w::Application::interrupted),"exact native interruption projects original queued command");
    const auto interrupted_item=Run(c,f,w::Verb::action_status,item);
    Check(interrupted_item.application==w::Application::interrupted
        &&interrupted_item.local_settlement==w::LocalSettlement::settled
        &&!(interrupted_item.flags&w::application_pending),"interruption does not erase queued receipt or fabricate cleanup");
    Check(!c.ObserveApplication(item_digest,w::Application::pending),"nonterminal projection rejected");
    auto second=context;second.context_id=Id(500);second.context_digest[0]^=2;
    Check(Run(c,f,w::Verb::attach_context,second).outcome==w::Outcome::bound,"new encounter under same parent");
    Run(c,f,w::Verb::context_status,context);
    auto power=item;power.action=w::Action::self_power;power.power_id=429545819;power.item_key[0]=power.item_key[1]=power.template_key[0]=power.template_key[1]=0;power.item_hint=power.template_hint=0;power.request=Id(12);
    f.local_pending=true;Run(c,f,w::Verb::submit,power);
    w::Digest power_digest{};Check(w::HashCommand(power,power_digest)&&c.ObserveApplication(power_digest),"native journal observes exact application");
    const auto effect=Run(c,f,w::Verb::action_status,power);
    Check(effect.application==w::Application::observed&&effect.local_settlement==w::LocalSettlement::pending,"observed effect never settles local native initiation");
    auto next=item;next.request=Id(13);const auto count=f.submits;
    Check(Run(c,f,w::Verb::submit,next).outcome==w::Outcome::deferred&&f.submits==count,"unsettled local action serializes all entry");
    a::Operation done;done.outcome=w::Outcome::queued;done.entry=w::Entry::entered;done.local=w::LocalSettlement::settled;done.history=w::outbound_queued;done.application=w::Application::observed;
    Check(c.UpdateAction(power,done),"exact positive local completion recorded");
    f.local_pending=false;next.request=Id(14);Check(Run(c,f,w::Verb::submit,next).outcome==w::Outcome::queued,"local settlement admits independent buff without waiting for remote effect");
    f.stop_pending=true;Check(Run(c,f,w::Verb::stop_owner,owner).owner_phase==w::Phase::stopping,"unresolved cleanup stays owned");
    auto denied=item;denied.request=Id(15);const auto previous=f.submits;
    Check(Run(c,f,w::Verb::submit,denied).outcome==w::Outcome::deferred&&f.submits==previous,"stopping owner never admits new work");
    f.stop_pending=false;Check(Run(c,f,w::Verb::stop_owner,owner).owner_phase==w::Phase::closed,"repeated exact stop settles owner");
    Check(Run(c,f,w::Verb::action_status,power).application==w::Application::observed,"owner closure preserves observed remote history");
    Check(!c.Busy(),"positive owner cleanup releases local responsibility");
    Check(Run(c,f,w::Verb::open_owner,owner).outcome==w::Outcome::closed&&f.opens==1,"closed owner cannot reopen");
    auto new_owner=owner;new_owner.parent_id=Id(600);new_owner.parent_digest[0]^=4;
    Run(c,f,w::Verb::open_owner,new_owner);
    auto simple=power;simple.parent_id=new_owner.parent_id;simple.parent_digest=new_owner.parent_digest;simple.request=Id(1);
    f.reuse=true;Check(Run(c,f,w::Verb::submit,simple).outcome==w::Outcome::power_reuse_blocked,"native reuse refusal retained");
    Check(Run(c,f,w::Verb::cancel_action,simple).outcome==w::Outcome::cancelled,"cancel reuse rejection remains no entry");f.reuse=false;
    for(unsigned n=2;n<280;++n){simple.request=Id(n);Run(c,f,w::Verb::submit,simple);}
    simple.request=Id(2);const auto before_replay=f.submits;
    Check(Run(c,f,w::Verb::submit,simple).outcome==w::Outcome::history_expired&&f.submits==before_replay,"evicted history never authorizes repeat entry");
    simple.request=Id(300);f.reenter=true;
    const auto interrupted=Run(c,f,w::Verb::submit,simple);
    Check(interrupted.owner_phase==w::Phase::stopping||interrupted.owner_phase==w::Phase::closed,"reentrant stop is not lost");
    Check(f.revokes>0,"cleanup revokes admission before native stop");

    a::Controller diagnostics;Fake df;
    Run(diagnostics,df,w::Verb::open_owner,owner);
    Run(diagnostics,df,w::Verb::submit,item);
    auto detailed=done;detailed.application=w::Application::pending;
    constexpr char message[]="actor_v3:dispatch:o1:n2q1";
    std::memcpy(detailed.detail.data(),message,sizeof(message));
    Check(diagnostics.UpdateAction(item,detailed),"record exact action diagnostic");
    Check(diagnostics.Diagnose(item)==detailed.detail,"exact command retains diagnostic");
    bool exact_only=true;
    for(std::size_t i=0;i<sizeof(item);++i){
        auto altered=item;reinterpret_cast<unsigned char*>(&altered)[i]^=1;
        exact_only&=diagnostics.Diagnose(altered)==std::array<char,73>{};
    }
    Check(exact_only,"every immutable command byte participates in diagnostic correlation");
    Check(diagnostics.UpdateScope(owner,{w::Phase::closed,w::Closure::local_released},true)
        &&!diagnostics.Busy(),"positive local release permits a later producer namespace");
    Check(diagnostics.Diagnose(item)==detailed.detail,"closed exact action retains diagnostic history");
    auto replacement=owner;++replacement.host.process;++replacement.host.creation;
    ++replacement.host.generation;++replacement.grant.generation;replacement.parent_digest[0]^=1;
    replacement.request=item.request;
    const auto expired=Run(diagnostics,df,w::Verb::stop_owner,replacement,false,false);
    Check(expired.outcome==w::Outcome::history_expired&&df.stops==0,
        "revoked replacement namespace does not borrow prior closure");
    Check(diagnostics.Diagnose(replacement)==std::array<char,73>{},
        "new producer STOP with reused IDs cannot leak old queued-action detail");
    Check(Run(diagnostics,df,w::Verb::open_owner,replacement).outcome==w::Outcome::bound&&df.opens==2,
        "current new producer can open the same parent ordinal after prior closure");
    Check(Run(diagnostics,df,w::Verb::action_status,item,false,false).outcome==w::Outcome::history_expired
        &&diagnostics.Diagnose(item)==std::array<char,73>{},"new namespace discards old action diagnostic history");

    a::Controller malformed;Fake mf;Run(malformed,mf,w::Verb::open_owner,owner);
    auto uncertain=item;uncertain.request=Id(1);mf.local_pending=true;Run(malformed,mf,w::Verb::submit,uncertain);
    a::Operation impossible;impossible.outcome=w::Outcome::queued;impossible.entry=w::Entry::unknown;
    impossible.local=w::LocalSettlement::settled;impossible.history=w::outbound_queued;
    Check(!malformed.UpdateAction(uncertain,impossible),"queued history cannot lose positive entry proof");
    Check(Run(malformed,mf,w::Verb::action_status,uncertain).local_settlement==w::LocalSettlement::pending,"invalid update preserves local responsibility");
    const auto entered=mf.submits;auto blocked=item;blocked.request=Id(2);
    Check(Run(malformed,mf,w::Verb::submit,blocked).outcome==w::Outcome::deferred&&mf.submits==entered,"malformed native result blocks new entry");
    impossible.entry=w::Entry::entered;impossible.history=0;
    Check(!malformed.UpdateAction(uncertain,impossible),"queued outcome without append history rejected");
    impossible.entry=w::Entry::never_entered;impossible.history=w::uncertain_history;impossible.outcome=w::Outcome::uncertain;
    Check(!malformed.UpdateAction(uncertain,impossible),"never entered cannot settle historical uncertainty");
    a::Controller tombstone;Fake tf;
    const auto never=Run(tombstone,tf,w::Verb::stop_owner,owner);
    Check(never.closure==w::Closure::never_bound&&never.closure_scope==w::ClosureScope::owner&&!tf.stops&&!tf.opens,"unopened fresh owner exact no-entry tombstone");
    Check(Run(tombstone,tf,w::Verb::open_owner,owner).outcome==w::Outcome::closed&&!tf.opens,"tombstone prevents late open replay");
    a::Controller unused_child;Fake uf;Run(unused_child,uf,w::Verb::open_owner,owner);
    const auto child_never=Run(unused_child,uf,w::Verb::stop_context,context);
    Check(child_never.closure==w::Closure::never_bound&&child_never.owner_phase==w::Phase::bound&&!uf.attaches&&!uf.stops,"fresh child stop proves never bound without stopping parent");
    Check(Run(unused_child,uf,w::Verb::attach_context,context).outcome==w::Outcome::closed&&!uf.attaches,"child tombstone prevents delayed attach");
    for(unsigned reason=7;reason<=11;++reason){
        a::Controller typed;Fake backend;backend.admission_reason=static_cast<w::Reason>(reason);
        Run(typed,backend,w::Verb::open_owner,owner);auto cmd=item;cmd.request=Id(1);
        Check(Run(typed,backend,w::Verb::submit,cmd).reason==backend.admission_reason,"typed admission refusal retained");
        const auto cancelled=Run(typed,backend,w::Verb::cancel_action,cmd);
        Check(cancelled.outcome==w::Outcome::cancelled&&cancelled.reason==w::Reason::none&&!backend.stops,
            "cancel of known no-entry refusal normalizes response without native cleanup");
        Run(typed,backend,w::Verb::stop_owner,owner);
        const auto history=Run(typed,backend,w::Verb::action_status,cmd);
        Check(history.outcome==w::Outcome::deferred&&history.reason==backend.admission_reason&&history.owner_phase==w::Phase::closed,
            "terminal status preserves original typed no-entry history");
    }
    std::printf("actor controller: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
