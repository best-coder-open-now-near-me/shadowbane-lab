#include "actor_action_native.h"
#include "combat_v2_wire.h" // Qualified UTF16/JSON identity digests only; no v2 commands.
#include "movement_native_image.h"
#include <cmath>
#include <cstdio>

namespace wonderbane::extension::actor {
namespace power=combat::power;
namespace melee=combat::melee;
namespace submission=combat::submission;
namespace party=combat::party;
namespace identity=combat::v2::wire;
namespace {
using O=wire::Outcome;using E=wire::Entry;using L=wire::LocalSettlement;
template<class T> bool Read(std::uintptr_t at,T& out) noexcept {
    if(at<0x10000 || at>0x7fff0000-sizeof(T)){return false;}
    __try{std::memcpy(&out,reinterpret_cast<const void*>(at),sizeof(T));return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
struct Text {
    std::array<std::uint16_t,64> units{};std::size_t count{};
    identity::Text View() const noexcept{return {units.data(),count};}
};
bool ReadText(std::uintptr_t field,Text& out) noexcept {
    std::array<std::uint32_t,3> span{},after{};
    if(!Read(field+4,span)||span[0]<0x10000||(span[0]&1)||span[1]<=span[0]
        ||span[2]<span[1]||span[2]-span[1]<2||span[2]>0x7fff0000
        ||((span[1]-span[0])&1)||span[1]-span[0]>128){return false;}
    out.count=(span[1]-span[0])/2;
    for(std::size_t i=0;i<out.count;++i){if(!Read(span[0]+i*2,out.units[i])){return false;}}
    std::uint16_t end{};
    return Read(span[1],end)&&!end&&Read(field+4,after)&&span==after;
}
bool ActorName(std::uintptr_t actor,const fence::ActorBinding& binding) noexcept {
    Text local{},server{};wire::Digest name{},shard{},owner{};identity::IdentityJson json;
    return ReadText(actor+0xc48,local)&&ReadText(actor+0xc90,server)
        &&identity::IdentityDigest(local.units.data(),local.count,name)&&name==binding.local_name
        &&identity::IdentityDigest(server.units.data(),server.count,shard)&&shard==binding.server
        &&json.Append('[')&&json.String(server.View())&&json.Literal(", ")&&json.String(local.View())
        &&json.Append(']')&&json.Finish(owner)&&owner==binding.owner;
}
bool PlayerName(std::uintptr_t target,const fence::ActorBinding& parent,const fence::ContextBinding& child) noexcept {
    Text name{},server{};wire::Digest name_hash{},server_hash{},entry{};identity::IdentityJson json;
    if(!ReadText(target+0xc48,name)||!ReadText(target+0xc90,server)
        ||!identity::IdentityDigest(name.units.data(),name.count,name_hash)||name_hash!=child.target_name
        ||!identity::IdentityDigest(server.units.data(),server.count,server_hash)||server_hash!=parent.server
        ||!json.Literal("[\"player\", ")||!json.String(server.View())||!json.Literal(", \"")){return false;}
    constexpr char hex[]="0123456789abcdef";
    for(std::size_t i=0;i<2;++i){
        if(i&&!json.Append(':')){return false;}
        for(int shift=28;shift>=0;shift-=4){if(!json.Append(hex[(child.target_key[i]>>shift)&15])){return false;}}
    }
    return json.Literal("\"]")&&json.Finish(entry)&&entry==child.entry;
}
NativeActor::Operation Result(O outcome,E entry=E::never_entered,L settlement=L::settled) noexcept {
    NativeActor::Operation result{};result.outcome=outcome;result.entry=entry;result.local_settlement=settlement;return result;
}
NativeActor::Operation Blocked(std::uint32_t blocks,const NativeActor::Observation& state={}) noexcept {
    auto result=Result(O::deferred);result.admission_blocks=blocks;result.reason=wire::AdmissionReason(blocks);result.state=state;return result;
}
}
std::uint32_t NativeActor::AdmissionBlocks(const Observation& state,bool owned_followup,bool stationary_self) noexcept {
    std::uint32_t blocks{};
    // Ordinary item and self-power entry do not require an empty protocol vector.
    // Only positively stationary state 5 permits retained bookkeeping here;
    // actual native Use keeps its legality checks. Targeted actions stay strict.
    if(!state.ClearInitiation()&&!owned_followup
        &&!(stationary_self&&state.initiation.state==5)){blocks|=admission::initiation;}
    if(stationary_self&&state.initiation.state!=5){blocks|=admission::initiation;}
    if(power::NativeUseInFlight()){blocks|=admission::native_use;}
    if(pending_||request_||transfer_){blocks|=admission::local_action;}
    if(state.target&&(!child_bound_||state.target!=reinterpret_cast<std::uintptr_t>(target_)
        ||!Current(true))){blocks|=admission::foreign_target;}
    return blocks;
}
bool NativeActor::ReadAdmission(std::uint32_t& blocks) noexcept {
    blocks=0;if(running_||faulted_){return false;}running_=true;bool result=false;
    __try{__try{result=ReadAdmissionImpl(blocks);}__finally{running_=false;}}
    __except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;blocks=0;}
    return result;
}
bool NativeActor::ReadAdmissionImpl(std::uint32_t& blocks) noexcept {
    blocks=0;Observation before{},after{};
    if(!SceneCurrent()||!ActorIdentity()||!ReadState(before)){return false;}
    const auto first=AdmissionBlocks(before,false,before.initiation.state==5);
    if(!ReadState(after)||before.target!=after.target||before.mode!=after.mode||before.initiation!=after.initiation
        ||first!=AdmissionBlocks(after,false,after.initiation.state==5)||!SceneCurrent()){return false;}
    blocks=first;return true;
}
bool NativeActor::Owner() const noexcept {
    DWORD process{};return thread_&&GetCurrentThreadId()==thread_
        &&GetWindowThreadProcessId(window_,&process)==thread_&&process==GetCurrentProcessId();
}
bool NativeActor::Available() const noexcept{return image_&&actor_&&!faulted_;}
bool NativeActor::RawCurrent() const noexcept {
    std::uintptr_t actor{},root{},world{};
    return Read(image_+0x16a2d98,actor)&&actor==scene_.actor
        &&Read(image_+0x16a7bfc,root)&&root==scene_.window
        &&Read(image_+0x1389028,world)&&world==scene_.world;
}
bool NativeActor::SceneCurrent() const noexcept {
    return Available()&&Owner()&&scene_current_&&scene_current_(scene_context_)
        &&movement::NativeMovementLifetimeCurrent(scene_)&&RawCurrent();
}
bool NativeActor::ActorIdentity() const noexcept {
    const auto actor=reinterpret_cast<std::uintptr_t>(actor_);
    std::uintptr_t table{},component{},pose{},parent{},getter{};
    std::array<std::uint32_t,2> key{};movement::GroundPoint point{};
    return actor==scene_.actor&&Read(actor,table)&&table==image_+0x114165c
        &&Read(actor+0x18,key)&&key==scene_.identity&&key[0]&&key[1]==53
        &&Read(table+0x58,getter)&&getter==image_+0xa3d0
        &&Read(actor+0x4b0,component)&&Read(component,pose)&&Read(pose+8,parent)&&parent==scene_.parent
        &&Read(pose+0x20,point)&&std::isfinite(point.x)&&std::isfinite(point.y)&&std::isfinite(point.z)
        &&point.x>=0&&point.x<=200000&&point.z<=0&&point.z>=-200000&&point.y>=-2000&&point.y<=20000;
}
bool NativeActor::BindCxx() noexcept {
    try {
        if(!scene_current_||!scene_current_(scene_context_)||!movement::NativeMovementLifetimeCurrent(scene_)||!RawCurrent()){return false;}
        auto** output=calls_.lookup(reinterpret_cast<void*>(scene_.world),&actor_,scene_.identity.data());
        if(output!=&actor_){faulted_=true;return false;}
        return SceneCurrent()&&ActorIdentity();
    }catch(...){faulted_=true;return false;}
}
bool NativeActor::BindScene(const movement::NativeScene& scene,HWND window,Admission current,void* context) noexcept {
    if(actor_||image_||faulted_||running_||!current||!scene.epoch){return false;}
    scene_=scene;window_=window;thread_=GetCurrentThreadId();scene_current_=current;scene_context_=context;
    if(!Owner()||!movement::VerifyNativeMovementImage(image_)){image_=0;return false;}
    calls_.lookup=reinterpret_cast<decltype(calls_.lookup)>(image_+0x1fcc80);
    calls_.release=reinterpret_cast<decltype(calls_.release)>(image_+0x89bd0);
    calls_.dispatch=reinterpret_cast<decltype(calls_.dispatch)>(image_+0x7ca9c0);
    calls_.attack=melee::Invoke;calls_.power=power::Invoke;calls_.track=power::InvokeTrack;calls_.chat=combat::group_chat::Invoke;calls_.self_initiation=power::ReadSelfInitiation;calls_.item=combat::item::Invoke;
    running_=true;bool ok=false;
    __try{ok=BindCxx();}__except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;}
    running_=false;
    if(!ok&&!faulted_){
        __try{if(!ClearCxx()){faulted_=true;}}__except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;}
        if(!faulted_){image_=0;}
    }
    return ok;
}
bool NativeActor::MatchesIdentity(const wire::Digest& local_name,const wire::Digest& server) const noexcept {
    Text name{},shard{};wire::Digest n{},s{};
    return SceneCurrent()&&ActorIdentity()&&ReadText(scene_.actor+0xc48,name)&&ReadText(scene_.actor+0xc90,shard)
        &&identity::IdentityDigest(name.units.data(),name.count,n)&&n==local_name
        &&identity::IdentityDigest(shard.units.data(),shard.count,s)&&s==server&&SceneCurrent();
}
bool NativeActor::ValidateParent(const fence::ActorBinding& binding,Gates gates) noexcept {
    if(running_||!SceneCurrent()||!ActorIdentity()||!fence::Valid(binding)||!gates.current||!gates.append_current
        ||binding.client_pid!=GetCurrentProcessId()||binding.client_creation!=fence::Creation(GetCurrentProcess())
        ||binding.scene!=scene_.epoch||binding.actor_hint!=scene_.actor||std::memcmp(binding.actor_key,scene_.identity.data(),8)
        ||!ActorName(scene_.actor,binding)||!gates.current(gates.context)||!SceneCurrent()){return false;}
    if(parent_bound_){return !revoked_&&fence::Same(parent_,binding);}
    if(pending_||local_owner_work_||local_context_work_||child_bound_){return false;}
    parent_=binding;parent_gates_=gates;parent_bound_=true;revoked_=false;return true;
}
bool NativeActor::TargetIdentity() const noexcept {
    const auto target=reinterpret_cast<std::uintptr_t>(target_);std::uintptr_t table{};party::Key key{};
    if(!target||target!=child_.target_hint||!Read(target,table)||table!=image_+0x114165c
        ||!Read(target+0x18,key)||std::memcmp(key.data(),child_.target_key,8)||key==scene_.identity){return false;}
    if(child_.authority==2){combat::policy::Snapshot snapshot{};
        return combat::policy::Capture(window_,image_,scene_,target_,key,snapshot)==combat::policy::Outcome::eligible
            &&party::Equal(snapshot.party,party_);}
    return child_.authority==1&&key[1]==53&&PlayerName(target,parent_,child_);
}
bool NativeActor::Current(bool child) noexcept {
    if(!parent_bound_||revoked_||!SceneCurrent()||!ActorIdentity()||!ActorName(scene_.actor,parent_)
        ||!parent_gates_.current||!parent_gates_.current(parent_gates_.context)){return false;}
    if(child){
        party::Snapshot fresh{};
        if(!child_bound_||!child_gates_.current||!child_gates_.current(child_gates_.context)
            ||!party::Capture(image_,scene_,fresh)||!party::Equal(fresh,party_)
            ||party::Protected(fresh,{child_.target_key[0],child_.target_key[1]})||!TargetIdentity()){return false;}
    }
    return SceneCurrent()&&parent_gates_.current(parent_gates_.context)
        &&(!child||child_gates_.current(child_gates_.context));
}
bool NativeActor::Gate(void* value) noexcept {
    auto& self=*static_cast<NativeActor*>(value);const bool child=wire::Any(self.command_.context_id);
    if(!self.Current(child)||power::NativeUseInFlight()){return false;}
    const bool entered=self.command_.action==wire::Action::attack?self.melee_receipt_.native_entered:
        self.command_.action==wire::Action::use_item?self.item_receipt_.native_entered:self.power_receipt_.native_entered;
    if(!entered){Observation state{};
        if(!self.pre_entry_epoch_||power::InitiationEpoch()!=self.pre_entry_epoch_||!self.ReadState(state)){return false;}
        const auto blocks=self.AdmissionBlocks(state,state.initiation.Only(self.pre_entry_self_id_),
            self.command_.action==wire::Action::use_item||self.command_.action==wire::Action::self_power);
        if(blocks&~admission::local_action){return false;}}
    return true;
}
bool NativeActor::AppendGate(void* value) noexcept {
    auto& self=*static_cast<NativeActor*>(value);
    return !self.faulted_&&!self.revoked_&&self.parent_bound_&&self.RawCurrent()
        &&self.parent_gates_.append_current&&self.parent_gates_.append_current(self.parent_gates_.context)
        &&(!wire::Any(self.command_.context_id)||(self.child_bound_&&self.child_gates_.append_current
            &&self.child_gates_.append_current(self.child_gates_.context)));
}
bool NativeActor::ChatGate(void* value) noexcept {
    auto& self=*static_cast<NativeActor*>(value);
    return !self.faulted_&&self.Current(false);
}
bool NativeActor::TrackGate(void* value) noexcept {
    auto& self=*static_cast<NativeActor*>(value);
    return !self.faulted_&&!power::NativeUseInFlight()&&!self.request_&&!self.transfer_&&self.Current(false);
}
bool NativeActor::TrackAppendGate(void* value) noexcept {
    auto& self=*static_cast<NativeActor*>(value);
    return !self.faulted_&&!self.revoked_&&self.parent_bound_&&self.RawCurrent()
        &&self.parent_gates_.append_current&&self.parent_gates_.append_current(self.parent_gates_.context);
}
bool NativeActor::SceneGate(void* value) noexcept{return static_cast<NativeActor*>(value)->SceneCurrent();}
void NativeActor::ClearInstant() noexcept {instant_self_id_=0;instant_self_epoch_=0;instant_definition_={};}
bool NativeActor::ReleaseMessages(){melee::Release(transfer_);melee::Release(request_);return !transfer_&&!request_;}
bool NativeActor::ReleaseTarget(){
    if(target_){calls_.release(&target_,nullptr);if(target_){faulted_=true;return false;}}
    child_bound_=false;child_={};child_gates_={};party_={};ClearInstant();return true;
}
bool NativeActor::ReleaseAll(){
    if(faulted_){return false;}
    if(!actor_buffs::Release(observation_state_)||!ReleaseMessages()||!ReleaseTarget()){faulted_=true;return false;}
    if(actor_){calls_.release(&actor_,nullptr);if(actor_){faulted_=true;return false;}}
    parent_bound_=false;parent_={};parent_gates_={};pending_=false;local_owner_work_=local_context_work_=false;return true;
}
bool NativeActor::ClearCxx() noexcept {try{return ReleaseAll();}catch(...){faulted_=true;return false;}}
bool NativeActor::ReleaseScene() noexcept {
    if(running_||faulted_||!Owner()||movement::NativeMovementLifetimeCurrent(scene_)){return false;}
    running_=true;bool ok=false;
    __try{ok=ClearCxx();}__except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;}
    running_=false;if(ok){image_=0;scene_={};scene_current_=nullptr;scene_context_=nullptr;revoked_=false;}return ok;
}
NativeActor::Operation NativeActor::AttachImpl(){
    if(power::NativeUseInFlight()||pending_){return Result(O::deferred);}
    if(!Current(false)||!party::Capture(image_,scene_,party_)||party::Protected(party_,{child_.target_key[0],child_.target_key[1]})){return Result(O::stale);}
    auto** output=calls_.lookup(reinterpret_cast<void*>(scene_.world),&target_,child_.target_key);
    if(output!=&target_){faulted_=true;return Result(O::uncertain,E::unknown,L::pending);}
    child_bound_=true;
    if(!Current(true)){return Result(O::stale);}
    Observation state{};if(!ReadState(state)){return Result(O::unavailable);}
    if(state.target!=reinterpret_cast<std::uintptr_t>(target_)&&(state.target||!state.ClearInitiation())){return Result(O::deferred);}
    local_context_work_=state.target==reinterpret_cast<std::uintptr_t>(target_);
    auto result=Result(O::bound);result.state=state;return result;
}
NativeActor::Operation NativeActor::Attach(const fence::ContextBinding& child,Gates gates) noexcept {
    if(running_||faulted_||!parent_bound_||!fence::Parent(child,parent_)||!gates.current||!gates.append_current){return Result(O::invalid);}
    if(child_bound_){return Result(fence::Same(child_,child)?O::bound:O::deferred);}
    if(target_){return Result(O::unavailable);}
    child_=child;child_gates_=gates;running_=true;stage_="attach";
    auto result=Guarded(1);running_=false;
    if(result.outcome!=O::bound&&!faulted_){
        running_=true;const auto released=Guarded(6);running_=false;
        if(!faulted_&&released.outcome==O::observed){result.closure=wire::Closure::local_released;}
        else{result=Result(O::uncertain,E::unknown,L::pending);result.history=wire::uncertain_history;}
    }
    return result;
}
NativeActor::Operation NativeActor::SubmitImpl(){
    const bool child=wire::Any(command_.context_id);
    if(power::NativeUseInFlight()||pending_){return Blocked((power::NativeUseInFlight()?admission::native_use:0U)|(pending_?admission::local_action:0U));}
    stage_="current";if(!Current(child)){return Result(O::stale);}
    if(!child&&(command_.action==wire::Action::self_power||command_.action==wire::Action::use_item)){
        std::uint32_t current_blocks{};
        if(!ReadAdmissionImpl(current_blocks)){return Blocked(0);}
        if(current_blocks){return Blocked(current_blocks);}
        if(command_.selector_index>=publication_.count||!RevalidatePublicationImpl(publication_)){return Blocked(0);}
        const auto& intent=publication_.actions[command_.selector_index].intent;
        if(intent.action_index!=command_.selector_index||intent.power_id!=command_.power_id){return Result(O::invalid);}
        if(command_.action==wire::Action::use_item){
            combat::inventory::Facts item{};
            const actor_effects::Context observed{image_,scene_.actor,scene_.identity,scene_.epoch,SceneGate,this};
            if(!actor_buffs::ItemOperand(observed,observation_state_,publication_,command_.selector_index,item)
                ||std::memcmp(item.item_key.data(),command_.item_key,8)||std::memcmp(item.template_key.data(),command_.template_key,8)
                ||item.item_address!=command_.item_hint||item.template_address!=command_.template_hint){return Result(O::stale);}
        }
    }
    const auto observed_epoch=power::InitiationEpoch();Observation state{};
    if(!ReadState(state)){return Result(O::unavailable);}
    if(state.ClearInitiation()||!state.initiation.Only(instant_self_id_)){ClearInstant();}
    bool owned_followup=false;
    if(command_.action==wire::Action::attack&&child&&instant_self_id_&&instant_self_epoch_
        &&power::InitiationEpoch()==instant_self_epoch_&&state.initiation.Only(instant_self_id_)){
        power::InitiationDefinition definition{};
        owned_followup=calls_.self_initiation(image_,scene_.actor,instant_self_id_,definition)
            &&definition==instant_definition_&&definition.seconds==0
            &&power::InitiationEpoch()==instant_self_epoch_&&Current(true);
    }
    const bool stationary_self=command_.action==wire::Action::use_item||command_.action==wire::Action::self_power;
    const auto blocks=AdmissionBlocks(state,owned_followup,stationary_self);
    if(blocks){return Blocked(blocks,state);}
    power::InitiationDefinition self_definition{};
    const bool instant=command_.action==wire::Action::self_power&&child&&state.ClearInitiation()
        &&calls_.self_initiation(image_,scene_.actor,command_.power_id,self_definition)&&self_definition.seconds==0;
    if(!Current(child)){return Result(O::stale);}
    Observation final{};
    if(!ReadState(final)||final!=state){return Blocked(0);}
    const auto final_blocks=AdmissionBlocks(final,owned_followup,stationary_self);if(final_blocks){return Blocked(final_blocks,final);}
    pre_entry_epoch_=owned_followup?instant_self_epoch_:observed_epoch;
    pre_entry_self_id_=owned_followup?instant_self_id_:0;
    if(!pre_entry_epoch_||power::InitiationEpoch()!=pre_entry_epoch_){return Blocked(0);}
    std::uintptr_t writer{},container{};stage_="writer";
    if(!Read(image_+0x16ab88c,writer)||!Read(writer+0x44,container)){return Result(O::unavailable);}
    stage_="dispatch";ClearInstant();
    Operation result{};
    if(command_.action==wire::Action::use_item){
        combat::item::Context context{image_,scene_.actor,writer,container,command_.item_hint,command_.template_hint,
            scene_.identity,{command_.item_key[0],command_.item_key[1]},
            {command_.template_key[0],command_.template_key[1]},8,10,Gate,AppendGate,this};
        context.activation=activation_;
        const auto receipt=calls_.item(context,item_state_,item_receipt_);
        if(receipt.ownership_quarantined){faulted_=true;}
        result=Result(receipt.append_observed?O::queued:receipt.native_entered?O::uncertain:O::rejected,
            receipt.native_entered?E::entered:E::never_entered,faulted_?L::pending:L::settled);
        result.history=(receipt.append_observed?wire::outbound_queued:0U)
            |((receipt.native_entered&&!receipt.append_observed)||faulted_?wire::uncertain_history:0U);
        // This exact ordinary type8/flagsA branch has no local mode/action/AF8
        // mutation. A normal return settles local ownership, not remote use.
    }else if(command_.action==wire::Action::attack){
        submission::Context context{};context.route=submission::Route::explicit_object;
        context.actor=scene_.actor;context.target=reinterpret_cast<std::uintptr_t>(target_);
        context.writer=writer;context.container=container;context.local_key=scene_.identity;
        context.target_key={child_.target_key[0],child_.target_key[1]};context.current=Gate;context.append_current=AppendGate;
        context.context=this;context.receipt=&melee_receipt_;
        submission::Scope scope(context);if(!Current(true)){return Result(O::stale);}
        dispatched_=true;local_context_work_=true;
        (void)calls_.attack(image_,actor_,target_,scope,request_,transfer_,Gate,this);
        const auto receipt=scope.Finish();
        const bool uncertain=!receipt.native_entered||receipt.result==submission::Result::uncertain||!Current(true);
        // The ordinary helper may change stance before the observed Factory.
        // Without that receipt, attempted dispatch is not positive entry proof.
        result=Result(uncertain?O::uncertain:receipt.append_observed?O::queued:O::rejected,
            receipt.native_entered?E::entered:E::unknown,uncertain?L::pending:L::settled);
        result.history=(receipt.append_observed?wire::outbound_queued:0U)|(uncertain?wire::uncertain_history:0U);
    }else{
        power::Context context{};context.image=image_;context.actor=scene_.actor;
        context.authority=child?power::Authority::engagement:power::Authority::actor;
        context.target=child?reinterpret_cast<std::uintptr_t>(target_):0;
        context.target_key=child?power::Key{child_.target_key[0],child_.target_key[1]}:power::Key{};
        context.target_mode=command_.action==wire::Action::self_power?power::TargetMode::self:power::TargetMode::engagement_object;
        context.actor_key=scene_.identity;context.writer=writer;context.container=container;context.power_id=command_.power_id;
        context.current=Gate;context.append_current=AppendGate;context.owner=this;context.receipt=&power_receipt_;
        context.activation=activation_;
        power::Scope scope(context);if(!Current(child)){return Result(O::stale);}
        dispatched_=true;(void)calls_.power(scope);const auto receipt=scope.Finish();
        if(!receipt.native_entered&&!receipt.append_observed){
            if(!Current(child)){return Result(O::stale);}
            if(receipt.availability!=power::Availability::unknown&&(!receipt.availability_epoch
                ||power::InitiationEpoch()!=receipt.availability_epoch)){return Result(O::deferred);}
            if(receipt.availability==power::Availability::reuse_blocked){result=Result(O::power_reuse_blocked);result.reason=wire::Reason::power_reuse;return result;}
            if(receipt.availability==power::Availability::global_recovery){result=Result(O::deferred);result.reason=wire::Reason::recovery;return result;}
            if(receipt.availability==power::Availability::stance_ineligible){result=Result(O::deferred);result.reason=wire::Reason::observation;return result;}
            return Result(receipt.availability==power::Availability::unknown?O::unavailable:O::rejected);
        }
        const bool good=receipt.append_observed&&receipt.followup_entered&&receipt.initiation_epoch
            &&receipt.result==power::Result::queued&&Current(child);
        result=Result(good?O::queued:O::uncertain,E::entered,L::pending);
        result.history=(receipt.append_observed?wire::outbound_queued:0U)|(!good?wire::uncertain_history:0U);
        pending_owned_followup_=good;pending_epoch_=good?receipt.initiation_epoch:0;
        pending_saw_initiation_=good; // Qualified normal followup appended this ID.
        if(child){local_context_work_=true;}else{local_owner_work_=true;}
        if(instant&&good&&power::InitiationEpoch()==receipt.initiation_epoch){
            power::InitiationDefinition after_definition{};Observation after{};
            if(calls_.self_initiation(image_,scene_.actor,command_.power_id,after_definition)
                &&after_definition==self_definition&&ReadState(after)&&after.initiation.Only(command_.power_id)
                &&power::InitiationEpoch()==receipt.initiation_epoch&&Current(true)){
                instant_self_id_=command_.power_id;instant_self_epoch_=receipt.initiation_epoch;instant_definition_=self_definition;
                result.local_settlement=L::settled;
            }
        }
    }
    (void)ReadState(result.state);
    if(result.local_settlement==L::pending){pending_=true;pending_command_=command_;pending_operation_=result;}
    return result;
}
NativeActor::Operation NativeActor::ChatImpl() {
    stage_="group_chat";
    if(!ChatGate(this)||!calls_.chat){return Result(O::deferred);}
    combat::party::Snapshot group{};wire::Digest digest{};
    const auto input=wire::Chat(chat_command_);
    if(!combat::party::Capture(image_,scene_,group)||!combat::group_chat::Identity(group,digest)
        ||digest!=input.group){return Result(O::stale);}
    std::uintptr_t writer{},container{};
    if(!Read(image_+0x16ab88c,writer)||!Read(writer+0x44,container)){return Result(O::unavailable);}
    combat::group_chat::Context context{image_,writer,container,group,{},ChatGate,TrackAppendGate,this};
    std::memcpy(context.text.data(),input.text.data(),input.length);
    (void)calls_.chat(context,chat_state_,chat_receipt_);
    const auto& receipt=chat_receipt_;
    auto result=Result(receipt.native_entered?O::uncertain:O::deferred,
        receipt.native_entered?E::entered:E::never_entered,
        receipt.ownership_quarantined?L::pending:L::settled);
    if(receipt.append_observed)result.history|=wire::outbound_queued;
    if(receipt.result==combat::group_chat::Result::queued&&receipt.native_entered&&receipt.append_observed
        &&!receipt.ownership_quarantined){result.outcome=O::queued;}
    else if(receipt.native_entered||receipt.ownership_quarantined)result.history|=wire::uncertain_history;
    if(receipt.ownership_quarantined){
        // Unknown constructor/destructor references are never replayed or released
        // through guessed cleanup. Preserve any older combat action separately.
        faulted_=true;local_owner_work_=true;result.entry=receipt.native_entered?E::entered:E::unknown;
    }
    (void)ReadState(result.state);return result;
}
NativeActor::Operation NativeActor::TrackImpl() {
    stage_="tracking_query";
    if(!TrackGate(this)){return Blocked(power::NativeUseInFlight()?admission::native_use:0U);}
    std::uintptr_t writer{},container{};
    if(!Read(image_+0x16ab88c,writer)||!Read(writer+0x44,container)||!calls_.track){return Result(O::unavailable);}
    power::Context context{image_,scene_.actor,0,writer,container,scene_.identity,{},track_command_.power_id,
        TrackGate,TrackAppendGate,this,&track_receipt_,power::TargetMode::track,power::Authority::actor};
    power::Scope scope(context);
    (void)calls_.track(scope);
    const auto receipt=scope.Finish();
    Operation result=Result(receipt.native_entered?O::uncertain:O::deferred,
        receipt.native_entered?E::entered:E::never_entered);
    if(receipt.append_observed){result.history|=wire::outbound_queued;}
    if(receipt.result==power::Result::queued&&receipt.native_entered&&receipt.append_observed
        &&receipt.observation.use_returned&&TrackGate(this)){result.outcome=O::queued;}
    else if(receipt.native_entered){result.history|=wire::uncertain_history;}
    // The normal Use return released its local message references. No cast,
    // initiation token or application is owned by this query. Existing pending
    // combat state is deliberately untouched, including its exact receipt.
    (void)ReadState(result.state);return result;
}
NativeActor::Operation NativeActor::Submit(const wire::Command& command,combat::activation::Handle activation) noexcept {
    if(running_||faulted_||!wire::Valid(wire::Verb::submit,command)||!parent_bound_
        ||!wire::Bindings(command,parent_,wire::Any(command.context_id)?&child_:nullptr)
        ||(wire::Any(command.context_id)&&!child_bound_)){return Result(O::invalid);}
    if(command.action==wire::Action::group_chat){
        if(activation||chat_state_.quarantined)return Result(O::unavailable,E::unknown,L::pending);
        chat_command_=command;chat_state_={};chat_receipt_={};running_=true;
        const auto result=Guarded(10);running_=false;return result;
    }
    if(command.action==wire::Action::track){
        if(activation||request_||transfer_||(pending_&&(!pending_owned_followup_
            ||pending_operation_.outcome!=O::queued||pending_operation_.entry!=E::entered
            ||!(pending_operation_.history&wire::outbound_queued)))){return Blocked(admission::local_action);}
        track_command_=command;track_receipt_={};running_=true;
        const auto result=Guarded(9);running_=false;return result;
    }
    if(pending_||request_||transfer_){return Blocked(admission::local_action);}
    if(activation&&activation.identity!=combat::activation::ActivationIdentity{scene_.actor,scene_.identity,scene_.epoch}){return Result(O::invalid);}
    command_=command;activation_=activation;running_=true;dispatched_=false;melee_receipt_={};power_receipt_={};item_receipt_={};item_state_={};
    pending_owned_followup_=false;pending_saw_initiation_=false;pending_epoch_=0;
    auto result=Guarded(2);running_=false;
    if(!faulted_&&(request_||transfer_)){
        running_=true;(void)Guarded(7);running_=false;
        if(faulted_){result.outcome=O::uncertain;result.local_settlement=L::pending;result.history|=wire::uncertain_history;}
    }
    if(result.local_settlement==L::pending){pending_=true;pending_command_=command;pending_operation_=result;}
    if(command.action==wire::Action::self_power||command.action==wire::Action::cast){result.power_diagnostic=power_receipt_;}
    combat::activation::RecordReturn(activation_,(result.history&wire::outbound_queued)!=0,pending_owned_followup_);
    return result;
}
NativeActor::Operation NativeActor::PollImpl(){
    if(!pending_){auto result=Result(O::observed);(void)ReadState(result.state);return result;}
    auto result=pending_operation_;const bool child=wire::Any(pending_command_.context_id);
    const bool lifetime=parent_.purpose==fence::Purpose::preparation
        ? parent_bound_&&SceneCurrent()&&ActorIdentity() : Current(child);
    if(!lifetime||power::NativeUseInFlight()||!ReadState(result.state)){return result;}
    // Empty initiation alone never proves settlement: only a positively observed
    // owned normal Use/followup can cross from local responsibility to clear.
    const auto activation=activation_?combat::activation::Read(activation_):combat::activation::Result::unknown;
    const bool terminal_activation=!request_&&!transfer_&&(activation==combat::activation::Result::completed
        ||activation==combat::activation::Result::interrupted||activation==combat::activation::Result::relinquished
        ||activation==combat::activation::Result::locally_completed);
    if(pending_owned_followup_&&pending_saw_initiation_&&pending_epoch_
        &&(parent_.purpose==fence::Purpose::preparation
            ? terminal_activation||power::ReadLocalInitiation(power_receipt_.local_initiation_token,scene_.actor,scene_.identity,pending_command_.power_id)==power::LocalInitiationState::retired
            : result.state.ClearInitiation())){
        result.local_settlement=L::settled;pending_=false;pending_operation_=result;
        if(!child){local_owner_work_=false;}
    }
    return result;
}
NativeActor::Operation NativeActor::Poll() noexcept {
    if(running_||faulted_){return pending_?pending_operation_:Result(O::unavailable,E::unknown,L::pending);}
    running_=true;stage_="poll";auto result=Guarded(3);running_=false;return result;
}
bool NativeActor::PendingCommand(wire::Command& out) const noexcept {if(!pending_){return false;}out=pending_command_;return true;}
bool NativeActor::ReadState(Observation& out) const noexcept {
    if(!SceneCurrent()||!ActorIdentity()){return false;}
    std::uintptr_t state{},after{};Observation first{},second{};
    auto capture=[&](Observation& value) noexcept {
        return Read(state+0x18,value.mode)&&Read(state+0x20,value.action_state)&&Read(scene_.actor+0x9bc,value.animation_event_index)
            &&combat::initiation::Capture(scene_.actor,state,value.initiation,[](std::uintptr_t at,auto& v)noexcept{return Read(at,v);})
            &&Read(scene_.actor+0xaf8,value.target)
            &&(!value.target||(value.target>=0x10000&&value.target<=0x7fff0000-4&&!(value.target&3)));
    };
    if(!Read(scene_.actor+0xad0,state)||state<0x10000||(state&3)||!capture(first)||!capture(second)||first!=second
        ||!Read(scene_.actor+0xad0,after)||state!=after||!SceneCurrent()){return false;}
    out=first;return true;
}
bool NativeActor::CombatTargetCurrent() const noexcept {
    Observation state{};return child_bound_&&target_&&ReadState(state)&&state.target==reinterpret_cast<std::uintptr_t>(target_);
}
bool NativeActor::ContinueContext() noexcept {
    if(running_||faulted_||!child_bound_){return false;}
    running_=true;stage_="continue_context";
    const auto result=Guarded(8);running_=false;
    return !faulted_&&result.outcome==O::observed;
}
NativeActor::Operation NativeActor::StopImpl(bool owner,Admission stop_current,void* context){
    if(!stop_current||!stop_current(context)||!SceneCurrent()||power::NativeUseInFlight()){return Result(O::pending,E::unknown,L::pending);}
    Observation state{};if(!ReadState(state)){return Result(O::pending,E::unknown,L::pending);}
    if(owner&&parent_.purpose==fence::Purpose::preparation){
        // Yielding preparation never cancels manual movement/combat. Only the
        // retained owned followup can settle; generic idle is not a substitute.
        if(pending_){(void)PollImpl();}
        if(pending_||local_owner_work_||local_context_work_||child_bound_||request_||transfer_){
            auto result=Result(O::pending,E::unknown,L::pending);result.state=state;return result;
        }
        if(!stop_current(context)||!SceneCurrent()){return Result(O::pending,E::unknown,L::pending);}
        parent_bound_=false;parent_={};parent_gates_={};ClearInstant();
        auto result=Result(O::closed,E::unknown,L::settled);result.state=state;
        result.closure=wire::Closure::local_released;return result;
    }
    const bool work=owner?(local_owner_work_||local_context_work_||pending_):local_context_work_;
    if(!owner&&pending_&&!wire::Any(pending_command_.context_id)&&work){return Result(O::pending,E::unknown,L::pending);}
    if(work){
        if(state.target&&(!child_bound_||state.target!=reinterpret_cast<std::uintptr_t>(target_))){return Result(O::pending,E::unknown,L::pending);}
        if(state.mode==2){
            const std::array<std::uint32_t,9> action{0x616};
            if(!stop_current(context)||!SceneCurrent()){return Result(O::pending,E::unknown,L::pending);}
            (void)calls_.dispatch(action.data(),reinterpret_cast<void*>(scene_.window));
        }
        if(!stop_current(context)||!ReadState(state)||state.mode!=1||!state.ClearInitiation()||state.target){
            auto result=Result(O::pending,E::unknown,L::pending);result.state=state;return result;}
    }
    if(!stop_current(context)||!SceneCurrent()){return Result(O::pending,E::unknown,L::pending);}
    if(!ReleaseMessages()||(!owner&&local_owner_work_&&pending_&&wire::Any(pending_command_.context_id))){return Result(O::pending,E::unknown,L::pending);}
    const bool closes_pending=pending_&&(owner||wire::Any(pending_command_.context_id));
    if(!ReleaseTarget()){return Result(O::uncertain,E::unknown,L::pending);}
    local_context_work_=false;ClearInstant();
    if(closes_pending){pending_=false;pending_operation_.local_settlement=L::settled;}
    if(owner){parent_bound_=false;parent_={};parent_gates_={};local_owner_work_=false;}
    auto result=Result(O::closed,E::unknown,L::settled);result.state=state;
    result.closure=work?wire::Closure::native_stopped:wire::Closure::local_released;return result;
}
NativeActor::Operation NativeActor::StopContext(const fence::ContextBinding& child,Admission gate,void* context) noexcept {
    if(running_||faulted_||!child_bound_||!fence::Same(child_,child)){return Result(O::unavailable,E::unknown,L::pending);}
    running_=true;stage_="stop_context";auto result=Guarded(4,gate,context);running_=false;return result;
}
NativeActor::Operation NativeActor::StopOwner(const fence::ActorBinding& parent,Admission gate,void* context) noexcept {
    if(running_||faulted_||!parent_bound_||!fence::Same(parent_,parent)){return Result(O::unavailable,E::unknown,L::pending);}
    revoked_=true;running_=true;stage_="stop_owner";auto result=Guarded(5,gate,context);running_=false;return result;
}
void NativeActor::Revoke() noexcept {revoked_=true;}
NativeActor::Operation NativeActor::RunCxx(unsigned operation,Admission gate,void* context) noexcept {
    try{
        switch(operation){case 1:return AttachImpl();case 2:return SubmitImpl();case 3:return PollImpl();
        case 9:return TrackImpl();case 10:return ChatImpl();
        case 4:return StopImpl(false,gate,context);case 5:return StopImpl(true,gate,context);
        case 6:if(!ReleaseTarget()){faulted_=true;}return Result(O::observed);
        case 7:if(!ReleaseMessages()){faulted_=true;}return Result(O::observed);
        case 8:{
            Observation before{},after{};
            if(!Current(true)||!ReadState(before)||!Current(true)||!ReadState(after)||before!=after
                ||(after.target&&after.target!=reinterpret_cast<std::uintptr_t>(target_))){return Result(O::stale);}
            return Result(O::observed);
        }
        default:return Result(O::invalid);}
    }catch(...){faulted_=true;return Result(O::uncertain,E::unknown,L::pending);}
}
NativeActor::Operation NativeActor::Guarded(unsigned operation,Admission gate,void* context) noexcept {
    submission::Boundary melee_boundary;power::Boundary power_boundary;Operation result{};
    __try{__try{result=RunCxx(operation,gate,context);}__finally{power_boundary.Restore();melee_boundary.Restore();}}
    __except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;result=Result(O::uncertain,E::unknown,L::pending);}
    if(faulted_&&operation==10){
        result.entry=chat_receipt_.native_entered?E::entered:E::unknown;
        result.local_settlement=L::pending;
        result.history|=wire::uncertain_history|(chat_receipt_.append_observed?wire::outbound_queued:0U);
    }
    if(faulted_&&operation==9){
        result.entry=track_receipt_.native_entered?E::entered:E::unknown;
        result.local_settlement=L::pending;
        result.history|=wire::uncertain_history|(track_receipt_.append_observed?wire::outbound_queued:0U);
    }
    if(faulted_&&(operation==2||operation==7)){
        const bool entered=command_.action==wire::Action::attack?melee_receipt_.native_entered:
            command_.action==wire::Action::use_item?item_receipt_.native_entered:power_receipt_.native_entered;
        result.entry=entered?E::entered:E::unknown;result.local_settlement=L::pending;
        result.history|=wire::uncertain_history|((melee_receipt_.append_observed||power_receipt_.append_observed||item_receipt_.append_observed)?wire::outbound_queued:0U);
    }
    const auto n=std::snprintf(result.detail.data(),result.detail.size(),"actor_v3:%s:o%u:n%uq%u",stage_,
        static_cast<unsigned>(result.outcome),static_cast<unsigned>(result.entry),static_cast<unsigned>((result.history&wire::outbound_queued)!=0));
    if(n<0||static_cast<std::size_t>(n)>=result.detail.size()){result.detail={};}return result;
}
actor_buffs::Unknown NativeActor::PublishImpl(const actor_buffs::Request& request,actor_buffs::Publication& out) noexcept {
    out={};publication_={};
    std::uint32_t before{};
    if(!ReadAdmissionImpl(before)){return actor_buffs::Unknown::identity;}
    if(!actor_buffs::Release(observation_state_)){faulted_=true;return actor_buffs::Unknown::inventory;}
    const actor_effects::Context context{image_,scene_.actor,scene_.identity,scene_.epoch,SceneGate,this};
    auto result=actor_buffs::Capture(context,request,observation_state_,out);
    std::uint32_t after{};
    if(result==actor_buffs::Unknown::none&&(!ReadAdmissionImpl(after)||before!=after)){result=actor_buffs::Unknown::changed;}
    if(result==actor_buffs::Unknown::none){out.admission_blocks=after;publication_=out;}else{out={};out.unknown=result;}
    return result;
}
actor_buffs::Unknown NativeActor::Publish(const actor_buffs::Request& request,actor_buffs::Publication& out) noexcept {
    if(running_||faulted_){out={};return actor_buffs::Unknown::identity;}
    running_=true;auto result=actor_buffs::Unknown::identity;
    __try{__try{result=PublishImpl(request,out);}__finally{running_=false;}}
    __except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;out={};publication_={};result=actor_buffs::Unknown::read_fault;}
    return result;
}
bool NativeActor::RevalidatePublication(const actor_buffs::Publication& out) noexcept {
    if(running_||faulted_){return false;}
    running_=true;bool result=false;
    __try{__try{result=RevalidatePublicationImpl(out);}__finally{running_=false;}}
    __except(EXCEPTION_EXECUTE_HANDLER){faulted_=true;}
    return result;
}
bool NativeActor::RevalidatePublicationImpl(const actor_buffs::Publication& out) noexcept {
    if(!SceneCurrent()||!ActorIdentity()){return false;}
    const actor_effects::Context context{image_,scene_.actor,scene_.identity,scene_.epoch,SceneGate,this};
    std::uint32_t blocks{};
    return actor_buffs::Revalidate(context,observation_state_,out)&&ReadAdmissionImpl(blocks)&&blocks==out.admission_blocks;
}
}
