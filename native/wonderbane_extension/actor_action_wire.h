#pragma once
#include "actor_action_fence.h"
#include "movement_wire.h"
#include "actor_admission.h"
namespace wonderbane::extension::actor::wire {
namespace m=::wonderbane::extension::movement;
using Digest=fence::Digest;using Id=fence::Id;
enum class Verb:std::uint32_t { open_owner=43,attach_context,submit,action_status,cancel_action,context_status,stop_context,owner_status,stop_owner,observe_actor,register_selectors };
enum class Action:std::uint32_t { none,attack,cast,self_power,use_item,track,group_chat };
enum class Recipient:std::uint32_t { none,actor,target };
enum class Outcome:std::uint32_t { observed,queued,stale,unavailable,invalid,pending,uncertain,exhausted,closed,rejected,bound,cancelled,deferred,history_expired,power_reuse_blocked };
enum class Phase:std::uint32_t { unknown,bound,stopping,closed,retired,blocked };
enum class Entry:std::uint32_t { unknown,never_entered,entered };
enum class LocalSettlement:std::uint32_t { unknown,pending,settled };
enum class Application:std::uint32_t { none,pending,observed,unknown,interrupted };
enum class Closure:std::uint32_t { none,never_bound,native_stopped,scene_retired,history_expired,local_released };
enum class ClosureScope:std::uint32_t { none,owner,context };
enum class Reason:std::uint32_t { none,power_reuse,recovery,initiation,stance,observation,item,target_occupied,local_action,native_use,child_cleanup,admission_changed,manual_activity };
constexpr std::uint32_t capability=0x80,admission_capability=0x100,preparation_capability=0x200,track_capability=0x400,group_chat_capability=0x800,no_selector=UINT32_MAX;
enum Flag:std::uint32_t { owner_cleanup=1,context_cleanup=2,outbound_queued=4,uncertain_history=8,application_pending=16 };
#pragma pack(push,1)
struct GroupChat {
    Digest group{};std::uint32_t length{};std::array<char,88> text{};
};
static_assert(sizeof(GroupChat)==124);
struct Command {
    m::wire::Host host{};std::uint64_t window{};m::wire::Grant grant{};
    Id request{},parent_id{},context_id{};Digest parent_digest{},context_digest{};
    Action action=Action::none;std::uint32_t power_id{},item_key[2]{},template_key[2]{},item_hint{};
    Recipient recipient=Recipient::none;std::uint32_t template_hint{},selector_index=no_selector;
    Digest manifest_digest{};std::uint64_t publication_revision{};Id snapshot_id{};
    std::uint32_t version=3;std::uint8_t reserved[124]{};
};
struct Receipt {
    Id request{};m::wire::Host host{};std::uint64_t window{};
    Outcome outcome=Outcome::unavailable;std::uint32_t flags{};m::wire::Grant grant{};
    Id parent_id{},context_id{};Digest command_digest{};
    std::uint32_t version=3;Verb verb=Verb::owner_status;Action action=Action::none;
    Entry entry=Entry::unknown;LocalSettlement local_settlement=LocalSettlement::unknown;
    Phase owner_phase=Phase::unknown,context_phase=Phase::unknown;Closure closure=Closure::none;
    Application application=Application::none;std::uint32_t mode{},action_state{},combat_target_present{};
    Reason reason=Reason::none;ClosureScope closure_scope=ClosureScope::none;
};
#pragma pack(pop)
static_assert(sizeof(Command)==576&&offsetof(Command,request)==240);
static_assert(offsetof(Command,manifest_digest)==392&&offsetof(Command,version)==448);
static_assert(sizeof(Receipt)==384&&offsetof(Receipt,command_digest)==296&&offsetof(Receipt,version)==328);
using fence::Any;
inline Reason AdmissionReason(std::uint32_t blocks) noexcept {
    return blocks&admission::manual_activity?Reason::manual_activity:blocks&admission::child_cleanup?Reason::child_cleanup:blocks&admission::local_action?Reason::local_action:
        blocks&admission::native_use?Reason::native_use:blocks&admission::foreign_target?Reason::target_occupied:
        blocks&admission::initiation?Reason::initiation:Reason::admission_changed;
}
inline bool Zero(const auto& value) noexcept{return m::wire::Zero(&value,sizeof(value));}
inline bool Owned(Phase p) noexcept{return p==Phase::bound||p==Phase::stopping||p==Phase::blocked;}
inline bool Closed(Phase p) noexcept{return p==Phase::closed||p==Phase::retired;}
inline bool ActionVerb(Verb v) noexcept{return v==Verb::submit||v==Verb::action_status||v==Verb::cancel_action;}
inline bool ReadVerb(Verb v) noexcept{return v==Verb::observe_actor||v==Verb::register_selectors;}
inline bool ContextVerb(Verb v) noexcept{return v==Verb::attach_context||v==Verb::context_status||v==Verb::stop_context;}
inline bool OwnerVerb(Verb v) noexcept{return v==Verb::open_owner||v==Verb::owner_status||v==Verb::stop_owner;}
inline bool ValidGrant(const m::wire::Grant& g,bool parent) noexcept {
    if(!parent||Zero(g)){return Zero(g);}m::Grant decoded{};
    return m::wire::Decode(g,decoded)&&decoded.owner==m::Owner::automation;
}
inline GroupChat Chat(const Command& c) noexcept {
    GroupChat out{};std::memcpy(&out,c.reserved,sizeof(out));return out;
}
inline bool ValidChat(const Command& c) noexcept {
    if(c.action!=Action::group_chat)return !Any(c.reserved);
    const auto chat=Chat(c);
    if(!Any(chat.group)||!chat.length||chat.length>chat.text.size())return false;
    for(std::size_t i=0;i<chat.text.size();++i){
        const auto ch=static_cast<unsigned char>(chat.text[i]);
        if(i>=chat.length){if(ch)return false;}
        else if(ch<32||ch>126||ch=='/'||ch=='\\'||ch=='^'||ch=='<'||ch=='>')return false;
    }
    return true;
}
inline bool Valid(const Command& c) noexcept {
    const bool parent=Any(c.parent_id),context=Any(c.context_id),selected=c.selector_index!=no_selector;
    if(c.version!=3||!ValidChat(c)||!m::wire::Valid(c.host)||!c.window||c.window>UINT32_MAX||!Any(c.request)
        ||parent!=Any(c.parent_digest)||context!=Any(c.context_digest)||(context&&(!parent||Zero(c.grant)))||!ValidGrant(c.grant,parent)
        ||c.action>Action::group_chat||c.recipient>Recipient::target
        ||selected!=Any(c.manifest_digest)||(selected&&c.selector_index>=32)
        ||(!selected&&(c.publication_revision||Any(c.snapshot_id)))
        ||static_cast<bool>(c.publication_revision)!=Any(c.snapshot_id)){return false;}
    const bool item=c.action==Action::use_item;
    if(item){if(!c.item_key[0]||!c.item_key[1]||!c.template_key[0]||c.template_key[1]
        ||!fence::Address(c.item_hint)||!fence::Address(c.template_hint)||c.item_hint==c.template_hint){return false;}}
    else if(!Zero(c.item_key)||!Zero(c.template_key)||c.item_hint||c.template_hint){return false;}
    if(static_cast<bool>(c.power_id)!=(c.action==Action::cast||c.action==Action::self_power||c.action==Action::track)){return false;}
    const auto recipient=c.action==Action::none?Recipient::none:
        ((c.action==Action::self_power||item||c.action==Action::track||c.action==Action::group_chat)?Recipient::actor:Recipient::target);
    return c.recipient==recipient&&!(recipient==Recipient::target&&!context)&&!(item&&context)
        &&!((c.action==Action::track||c.action==Action::group_chat)&&(context||selected))
        &&!(c.action!=Action::none&&!parent)
        &&!((c.action==Action::self_power||item)&&!context&&(!selected||!c.publication_revision));
}
inline bool Valid(Verb v,const Command& c) noexcept {
    if(v<Verb::open_owner||v>Verb::register_selectors||!Valid(c)||ActionVerb(v)!=(c.action!=Action::none)){return false;}
    if((c.action==Action::track||c.action==Action::group_chat)&&v==Verb::cancel_action){return false;}
    if(ReadVerb(v)){if(Any(c.parent_id)||!Zero(c.grant)||(v==Verb::register_selectors&&c.selector_index==no_selector)){return false;}}
    else if(!Any(c.parent_id)){return false;}
    return !(ContextVerb(v)&&!Any(c.context_id))&&!(OwnerVerb(v)&&Any(c.context_id));
}
inline bool HashCommand(const Command& c,Digest& out) noexcept{return Valid(c)&&fence::Hash(&c,sizeof(c),out);}
inline bool Bindings(const Command& c,const fence::ActorBinding& p,const fence::ContextBinding* child=nullptr) noexcept {
    Digest hash{},operation{};
    if(!Valid(c)||!fence::HashBinding(p,hash)||c.parent_digest!=hash||c.parent_id!=p.owner_id
        ||c.host.process!=p.producer_pid||c.host.creation!=p.producer_creation||c.host.generation!=p.producer_generation
        ){return false;}
    if(p.purpose==fence::Purpose::preparation){
        if(!Zero(c.grant)||Any(c.context_id)||!fence::Hash(p.owner_id.data(),p.owner_id.size(),operation)
            ||operation!=p.operation){return false;}
    }else if(Zero(c.grant)||c.grant.generation!=p.movement_generation||c.grant.scene!=p.scene
        ||!fence::Hash(&c.grant.token,sizeof(c.grant.token),operation)||operation!=p.operation){return false;}
    if(!Any(c.context_id)){return !child;}
    return child&&fence::Parent(*child,p)&&fence::HashBinding(*child,hash)
        &&c.context_digest==hash&&c.context_id==child->context_id;
}
inline bool Valid(const Receipt& r) noexcept {
    const bool parent=Any(r.parent_id),context=Any(r.context_id);
    if(context&&Zero(r.grant)){return false;}
    if(r.version!=3||r.verb<Verb::open_owner||r.verb>Verb::register_selectors||r.action>Action::group_chat
        ||r.outcome>Outcome::power_reuse_blocked||r.entry>Entry::entered||r.local_settlement>LocalSettlement::settled
        ||r.owner_phase>Phase::blocked||r.context_phase>Phase::blocked||r.closure>Closure::local_released
        ||r.application>Application::interrupted||r.reason>Reason::manual_activity||r.closure_scope>ClosureScope::context
        ||!m::wire::Valid(r.host)||!r.window||r.window>UINT32_MAX||!Any(r.request)||!Any(r.command_digest)
        ||r.flags&~31U||r.combat_target_present>1||!ValidGrant(r.grant,parent)
        ||ActionVerb(r.verb)!=(r.action!=Action::none)
        ||static_cast<bool>(r.flags&owner_cleanup)!=Owned(r.owner_phase)
        ||static_cast<bool>(r.flags&context_cleanup)!=Owned(r.context_phase)){return false;}
    if(!parent){if(context||r.owner_phase!=Phase::unknown||!ReadVerb(r.verb)){return false;}}
    else if(ReadVerb(r.verb)){return false;}
    if(((r.action==Action::attack||r.action==Action::cast)&&!context)||((r.action==Action::use_item||r.action==Action::track||r.action==Action::group_chat)&&context)){return false;}
    if((r.action==Action::track||r.action==Action::group_chat)&&r.verb==Verb::cancel_action){return false;}
    if((!context&&r.context_phase!=Phase::unknown)||(ContextVerb(r.verb)&&!context)||(OwnerVerb(r.verb)&&context)
        ||(Owned(r.context_phase)&&!Owned(r.owner_phase))){return false;}
    const auto history=r.flags&(outbound_queued|uncertain_history);
    if(r.action==Action::none&&(history||r.entry!=Entry::unknown||r.local_settlement!=LocalSettlement::unknown)){return false;}
    if((r.flags&outbound_queued)&&r.entry!=Entry::entered){return false;}
    if(r.entry==Entry::never_entered&&(history||r.application!=Application::none||r.local_settlement!=LocalSettlement::settled)){return false;}
    if(r.outcome==Outcome::queued&&!(r.flags&outbound_queued)){return false;}
    if(static_cast<bool>(r.flags&application_pending)!=(r.application==Application::pending||r.application==Application::unknown)){return false;}
    if(r.application==Application::interrupted&&(r.entry!=Entry::entered||!(r.flags&outbound_queued))){return false;}
    if(r.application!=Application::none&&r.action!=Action::cast&&r.action!=Action::self_power&&r.action!=Action::use_item){return false;}
    if((r.outcome==Outcome::history_expired)!=(r.closure==Closure::history_expired)){return false;}
    if(r.closure_scope==ClosureScope::context&&Closed(r.owner_phase)){return false;}
    if(r.closure_scope==ClosureScope::owner&&Closed(r.context_phase)&&r.context_phase!=r.owner_phase){return false;}
    if(r.closure==Closure::history_expired&&r.closure_scope!=ClosureScope::none){return false;}
    const auto phase=r.closure_scope==ClosureScope::owner?r.owner_phase:r.context_phase;
    if(r.closure==Closure::none){if(r.closure_scope!=ClosureScope::none||Closed(r.owner_phase)||Closed(r.context_phase)){return false;}}
    else if(r.closure==Closure::history_expired){
        if(r.outcome!=Outcome::history_expired||r.flags||r.entry!=Entry::unknown||r.owner_phase!=Phase::unknown
            ||r.context_phase!=Phase::unknown||r.local_settlement!=LocalSettlement::unknown){return false;}
    }else{
        if(r.closure_scope==ClosureScope::none||phase!=(r.closure==Closure::scene_retired?Phase::retired:Phase::closed)
            ||(r.closure_scope==ClosureScope::context&&!context)
            ||(r.closure==Closure::native_stopped&&(r.mode!=1||r.combat_target_present))
            ||(r.closure==Closure::never_bound&&r.entry==Entry::entered)){return false;}
        if(r.action!=Action::none&&r.local_settlement!=LocalSettlement::settled){return false;}
        if(r.closure==Closure::never_bound&&r.action!=Action::none&&r.entry!=Entry::never_entered){return false;}
    }
    if((r.outcome==Outcome::deferred||r.outcome==Outcome::cancelled||r.outcome==Outcome::power_reuse_blocked)
        &&r.action!=Action::none&&(r.entry!=Entry::never_entered||r.local_settlement!=LocalSettlement::settled||history)){return false;}
    if(r.outcome==Outcome::power_reuse_blocked){
        if((r.action!=Action::cast&&r.action!=Action::self_power)||(r.verb!=Verb::submit&&r.verb!=Verb::action_status)
            ||r.reason!=Reason::power_reuse||r.owner_phase==Phase::unknown){return false;}
    }else if(r.reason==Reason::power_reuse){return false;}
    if(r.reason>=Reason::target_occupied && ((r.verb!=Verb::submit&&r.verb!=Verb::action_status)||r.action==Action::none
        ||r.entry!=Entry::never_entered||r.local_settlement!=LocalSettlement::settled||history
        ||r.application!=Application::none||r.outcome!=Outcome::deferred)){return false;}
    return true;
}
inline bool Correlated(const Command& c,Verb v,const Receipt& r) noexcept {
    Digest hash{};return Valid(v,c)&&Valid(r)&&HashCommand(c,hash)&&r.command_digest==hash&&r.request==c.request
        &&r.parent_id==c.parent_id&&r.context_id==c.context_id&&r.action==c.action&&r.verb==v
        &&r.window==c.window&&!std::memcmp(&r.host,&c.host,sizeof(c.host))&&!std::memcmp(&r.grant,&c.grant,sizeof(c.grant));
}
inline Receipt Reply(const Command& c,Verb v,Outcome result) noexcept {
    Receipt r{};r.request=c.request;r.host=c.host;r.window=c.window;r.outcome=result;r.grant=c.grant;
    r.parent_id=c.parent_id;r.context_id=c.context_id;(void)HashCommand(c,r.command_digest);r.verb=v;r.action=c.action;return r;
}
}
