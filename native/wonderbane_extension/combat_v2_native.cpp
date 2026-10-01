#include "combat_v2_native.h"
#include "movement_native_image.h"
#include <cmath>
#include <cstdio>

namespace wonderbane::extension::combat::v2 {
namespace {
template<class T> bool Read(std::uintptr_t at, T& out) noexcept {
    if (at < 0x10000 || at > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(at), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Text {
    std::array<std::uint16_t, 64> units{};
    std::size_t count = 0;
    wire::Text View() const noexcept { return {units.data(), count}; }
};
bool ReadText(std::uintptr_t field, Text& out) noexcept {
    std::uintptr_t begin = 0, end = 0, capacity = 0;
    if (!Read(field + 4, begin) || !Read(field + 8, end) || !Read(field + 12, capacity)
        || begin < 0x10000 || begin % 2 || end <= begin || capacity < end || capacity - end < 2
        || capacity > 0x7fff0000 || (end - begin) % 2 || end - begin > 128) { return false; }
    out.count = (end - begin) / 2;
    for (std::size_t i = 0; i < out.count; ++i) {
        if (!Read(begin + i * 2, out.units[i])) { return false; }
    }
    std::uint16_t terminator = 1;
    if (!Read(end, terminator) || terminator) { return false; }
    std::uintptr_t after_begin = 0, after_end = 0, after_capacity = 0;
    return Read(field + 4, after_begin) && Read(field + 8, after_end)
        && Read(field + 12, after_capacity) && begin == after_begin
        && end == after_end && capacity == after_capacity;
}
using O = wire::Outcome;
}
bool NativeTarget::Owner() const noexcept {
    DWORD process = 0;
    return thread_ && GetCurrentThreadId() == thread_
        && GetWindowThreadProcessId(window_, &process) == thread_ && process == GetCurrentProcessId();
}
bool NativeTarget::Bind(HWND window) noexcept {
    if (base_ || faulted_) { return false; }
    window_ = window; thread_ = GetCurrentThreadId();
    if (!Owner() || !movement::VerifyNativeMovementImage(base_)) { base_ = 0; return false; }
    calls_.attack = &melee::Invoke; calls_.cast = &power::Invoke; calls_.self_initiation = &power::ReadSelfInitiation;
    calls_.lookup = reinterpret_cast<decltype(calls_.lookup)>(base_ + 0x1fcc80);
    calls_.retain = reinterpret_cast<decltype(calls_.retain)>(base_ + 0x131190);
    calls_.release = reinterpret_cast<decltype(calls_.release)>(base_ + 0x89bd0);
    calls_.dispatch = reinterpret_cast<decltype(calls_.dispatch)>(base_ + 0x7ca9c0);
    return true;
}
bool NativeTarget::RawCurrent() const noexcept {
    std::uintptr_t actor = 0, root = 0, world = 0;
    return Read(base_ + 0x16a2d98, actor) && actor == scene_.actor
        && Read(base_ + 0x16a7bfc, root) && root == scene_.window
        && Read(base_ + 0x1389028, world) && world == scene_.world;
}
bool NativeTarget::Identity() const noexcept {
    const auto actor=reinterpret_cast<std::uintptr_t>(actor_), target=reinterpret_cast<std::uintptr_t>(target_);
    std::uintptr_t actor_table{},target_table{}; std::array<std::uint32_t,2> actor_key{},target_key{};
    Text local_name{},server{};
    if(actor!=scene_.actor || actor!=command_.actor_hint || !target || target!=command_.target_hint
        || !Read(actor,actor_table) || actor_table!=base_+0x114165c
        || !Read(target,target_table) || target_table!=actor_table
        || !Read(actor+0x18,actor_key) || !Read(target+0x18,target_key)
        || std::memcmp(actor_key.data(),command_.local_key,8) || std::memcmp(target_key.data(),command_.target_key,8)
        || actor_key[1]!=53 || actor_key==target_key
        || !ReadText(actor+0xc48,local_name) || !ReadText(actor+0xc90,server)
        || !wire::ActorIdentityMatches(command_,local_name.View(),server.View())) { return false; }
    if(command_.authority==wire::Authority::npc) {
        policy::Snapshot snapshot{};
        return policy::Capture(window_,base_,scene_,target_,target_key,snapshot)==policy::Outcome::eligible
            && party::Equal(snapshot.party,party_);
    }
    Text target_name{},target_server{};
    return command_.authority==wire::Authority::manual_player && target_key[1]==53
        && ReadText(target+0xc48,target_name) && ReadText(target+0xc90,target_server)
        && wire::IdentitiesMatch(command_,local_name.View(),server.View(),target_name.View(),target_server.View());
}
bool NativeTarget::Current() noexcept {
    if (!Available() || !Owner() || !current_ || !current_(context_)
        || !movement::NativeMovementLifetimeCurrent(scene_) || !RawCurrent()) { return false; }
    party::Snapshot fresh{};
    return party::Capture(base_, scene_, fresh) && party::Equal(party_, fresh)
        && !party::Protected(fresh, {command_.target_key[0], command_.target_key[1]})
        && (!target_ || Identity()) && RawCurrent()
        && current_(context_) && movement::NativeMovementLifetimeCurrent(scene_);
}
bool NativeTarget::Gate(void* context) noexcept {
    auto& self=*static_cast<NativeTarget*>(context);
    if(!self.Current() || power::NativeUseInFlight()) { return false; }
    const bool entered=self.command_.action==wire::Action::attack
        ? self.submission_receipt_.native_entered : self.power_receipt_.native_entered;
    if(!entered) {
        Observation state{};
        if(!self.pre_entry_epoch_ || power::InitiationEpoch()!=self.pre_entry_epoch_
            || !self.ReadState(self.scene_,state)
            || (!state.ClearInitiation() && !state.initiation.Only(self.pre_entry_self_id_))) { return false; }
    }
    return true;
}
bool NativeTarget::AppendGate(void* context) noexcept {
    auto& self = *static_cast<NativeTarget*>(context);
    // Executed under the native outbound queue lock. No runtime/party/fence lock,
    // BCrypt, native call or allocation is permitted here. Native action already won entry.
    return !self.faulted_ && self.append_current_ && self.append_current_(self.context_)
        && self.RawCurrent();
}
bool NativeTarget::Position(movement::GroundPoint& point) const noexcept {
    std::uintptr_t component = 0, pose = 0, parent = 0, table = 0, getter = 0;
    return Read(scene_.actor, table) && Read(table + 0x58, getter) && getter == base_ + 0xa3d0
        && Read(scene_.actor + 0x4b0, component) && Read(component, pose)
        && Read(pose + 8, parent) && parent == scene_.parent && Read(pose + 0x20, point)
        && std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z)
        && point.x >= 0 && point.x <= 200000 && point.z <= 0 && point.z >= -200000
        && point.y >= -2000 && point.y <= 20000;
}
bool NativeTarget::Retain(void*& value) {
    const auto object = reinterpret_cast<std::uintptr_t>(value);
    std::uintptr_t table = 0; std::int32_t offset = 0;
    if (!Read(object + 8, table) || !Read(table + 4, offset)) { return false; }
    const auto adjusted = static_cast<std::int64_t>(object) + 8 + offset;
    if (adjusted < 0x10000 || adjusted > 0x7fff0000 - 8 || adjusted % 4) { return false; }
    calls_.retain(reinterpret_cast<void*>(static_cast<std::uintptr_t>(adjusted)), &value);
    return true;
}
void NativeTarget::ClearImpl() {
    if (faulted_) { return; }
    instant_self_id_=0; instant_self_epoch_=0; instant_self_definition_={};
    melee::Release(transfer_);
    melee::Release(request_);
    if (target_) { calls_.release(&target_, nullptr); }
    if (actor_) { calls_.release(&actor_, nullptr); }
}
bool NativeTarget::ClearMessagesCxx() noexcept {
    try { melee::Release(transfer_); melee::Release(request_); return true; }
    catch(...) { faulted_=true; return false; }
}
bool NativeTarget::ClearCxx() noexcept {
    try { ClearImpl(); return !faulted_; }
    catch (...) { faulted_ = true; return false; }
}
bool NativeTarget::Clear() noexcept {
    if (faulted_ || !Owner() || running_) { return false; }
    running_ = true;
    bool result = false;
    __try { result = ClearCxx(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; }
    running_ = false;
    return result;
}
Operation NativeTarget::PrepareImpl() {
    if(power::NativeUseInFlight()) { return {O::deferred}; }
    stage_="party_snapshot";
    if(!party::Capture(base_,scene_,party_) || party::Protected(party_,{command_.target_key[0],command_.target_key[1]})) { return {O::stale}; }
    if(!Current() || scene_.actor!=command_.actor_hint) { return {O::stale}; }
    actor_=reinterpret_cast<void*>(scene_.actor); stage_="actor_retain";
    if(!Retain(actor_)) { actor_=nullptr; return {O::unavailable}; }
    movement::GroundPoint point{}; stage_="position";
    if(!Current() || !Position(point)) { return {O::stale}; }
    stage_="registry_lookup";
    auto** result=calls_.lookup(reinterpret_cast<void*>(scene_.world),&target_,command_.target_key);
    if(result!=&target_) { faulted_=true; return {O::unavailable}; }
    stage_="target_identity";
    if(!target_ || !Current() || !Identity()) { return {O::stale}; }
    Observation state{}; stage_="existing_action";
    if(!ReadState(scene_,state)) { return {O::unavailable}; }
    // Adoption observes only the actual retained combat pointer. Unknown casts
    // are preserved without input; their target is never inferred from selection.
    if(state.target!=reinterpret_cast<std::uintptr_t>(target_)
        && (state.target || !state.ClearInitiation())) { return {O::deferred}; }
    return {O::bound};
}
Operation NativeTarget::Run() {
    if(preparing_) { return PrepareImpl(); }
    if(power::NativeUseInFlight()) { return {O::deferred,wire::Entry::never_entered}; }
    stage_="action_current";
    if(!Current()) { return {O::stale,wire::Entry::never_entered}; }
    const auto observed_epoch=power::InitiationEpoch();
    Observation observation{};
    if(!ReadState(scene_,observation)) { return {O::unavailable,wire::Entry::never_entered}; }
    if(observation.ClearInitiation() || !observation.initiation.Only(instant_self_id_)) {
        instant_self_id_=0; instant_self_epoch_=0; instant_self_definition_={};
    }
    bool owned_followup=false;
    if(command_.action==wire::Action::attack && instant_self_id_
        && observation.initiation.Only(instant_self_id_)
        && instant_self_epoch_ && power::InitiationEpoch()==instant_self_epoch_) {
        power::InitiationDefinition current_definition{};
        owned_followup=calls_.self_initiation(base_,scene_.actor,instant_self_id_,current_definition)
            && current_definition==instant_self_definition_ && current_definition.seconds==0
            && power::InitiationEpoch()==instant_self_epoch_ && Current();
    }
    if(command_.action==wire::Action::attack && !owned_followup) { instant_self_id_=0; instant_self_epoch_=0; instant_self_definition_={}; }
    if((!observation.ClearInitiation() && !owned_followup)
        || (observation.target && observation.target!=reinterpret_cast<std::uintptr_t>(target_))) {
        return {O::deferred,wire::Entry::never_entered};
    }
    power::InitiationDefinition self_definition{};
    const bool qualify_self=command_.action==wire::Action::self_power && observation.ClearInitiation()
        && calls_.self_initiation(base_,scene_.actor,command_.power_id,self_definition)
        && self_definition.seconds==0;
    if(!Current()) { return {O::stale,wire::Entry::never_entered}; }
    Observation final_observation{};
    if(!ReadState(scene_,final_observation) || final_observation!=observation) {
        return {O::deferred,wire::Entry::never_entered};
    }
    pre_entry_epoch_=owned_followup?instant_self_epoch_:observed_epoch;
    pre_entry_self_id_=owned_followup?instant_self_id_:0;
    if(!pre_entry_epoch_ || power::InitiationEpoch()!=pre_entry_epoch_) {
        return {O::deferred,wire::Entry::never_entered};
    }
    std::uintptr_t writer{},container{}; stage_="writer";
    if(!Read(base_+0x16ab88c,writer) || !Read(writer+0x44,container)) { return {O::unavailable,wire::Entry::never_entered}; }
    stage_="dispatch";
    if(command_.action==wire::Action::attack) {
        submission::Context context{};
        context.route=submission::Route::explicit_object;
        context.actor=scene_.actor; context.target=reinterpret_cast<std::uintptr_t>(target_);
        context.writer=writer; context.container=container;
        std::memcpy(context.local_key.data(),command_.local_key,8); std::memcpy(context.target_key.data(),command_.target_key,8);
        context.current=Gate; context.append_current=AppendGate; context.context=this; context.receipt=&submission_receipt_;
        submission::Scope scope(context);
        if(!Current()) { return {O::stale,wire::Entry::never_entered}; }
        instant_self_id_=0; instant_self_epoch_=0; instant_self_definition_={};
        dispatched_=true; // Includes the ordinary pre-D0 stance transition.
        (void)calls_.attack(base_,actor_,target_,scope,request_,transfer_,Gate,this);
        const auto receipt=scope.Finish();
        const bool queued=receipt.append_observed;
        const bool uncertain=receipt.result==submission::Result::uncertain || !Current();
        return {uncertain?O::uncertain:queued?O::client_outbound_queued:O::native_rejected,
            wire::Entry::entered,(queued?wire::outbound_queued:0U)|(uncertain?wire::uncertain_history:0U)};
    }
    power::Context context{};
    context.image=base_; context.actor=scene_.actor; context.target=reinterpret_cast<std::uintptr_t>(target_);
    context.writer=writer; context.container=container; context.power_id=command_.power_id;
    context.target_mode=command_.action==wire::Action::self_power
        ? power::TargetMode::self : power::TargetMode::engagement_object;
    std::memcpy(context.actor_key.data(),command_.local_key,8); std::memcpy(context.target_key.data(),command_.target_key,8);
    context.current=Gate; context.append_current=AppendGate; context.owner=this; context.receipt=&power_receipt_;
    power::Scope scope(context);
    if(!Current()) { return {O::stale,wire::Entry::never_entered}; }
    instant_self_id_=0; instant_self_epoch_=0; instant_self_definition_={};
    dispatched_=true;
    (void)calls_.cast(scope);
    const auto receipt=scope.Finish();
    const bool queued=receipt.append_observed;
    const bool uncertain=receipt.native_entered && (receipt.result==power::Result::uncertain || !Current());
    if(qualify_self && queued && !uncertain && receipt.followup_entered && receipt.initiation_epoch
        && power::InitiationEpoch()==receipt.initiation_epoch && Current()) {
        power::InitiationDefinition after_definition{}; Observation after{};
        if(calls_.self_initiation(base_,scene_.actor,command_.power_id,after_definition)
            && after_definition==self_definition && ReadState(scene_,after)
            && after.initiation.Only(command_.power_id)
            && power::InitiationEpoch()==receipt.initiation_epoch && Current()) {
            instant_self_id_=command_.power_id; instant_self_epoch_=receipt.initiation_epoch; instant_self_definition_=self_definition;
        }
    }
    return {uncertain?O::uncertain:queued?O::client_outbound_queued:O::native_rejected,
        receipt.native_entered?wire::Entry::entered:wire::Entry::never_entered,
        (queued?wire::outbound_queued:0U)|(uncertain?wire::uncertain_history:0U)};
}
Operation NativeTarget::RunCxx() noexcept {
    try { return Run(); }
    catch(...) { faulted_=true; return {O::uncertain,wire::Entry::unknown,wire::uncertain_history}; }
}
Operation NativeTarget::Guarded() noexcept {
    submission::Boundary melee_boundary; power::Boundary power_boundary;
    Operation result{};
    __try {
        __try { result=RunCxx(); }
        __finally { power_boundary.Restore(); melee_boundary.Restore(); }
    } __except(EXCEPTION_EXECUTE_HANDLER) { faulted_=true; result={O::uncertain,wire::Entry::unknown,wire::uncertain_history}; }
    if(faulted_) {
        const bool entered=command_.action==wire::Action::attack?dispatched_:power_receipt_.native_entered;
        const bool queued=submission_receipt_.append_observed || power_receipt_.append_observed;
        result.entry=entered?wire::Entry::entered:wire::Entry::unknown;
        result.history=wire::uncertain_history|(queued?wire::outbound_queued:0U);
    }
    const int length=std::snprintf(result.detail.data(),result.detail.size(),"combat_v2:%s:o%u:d%un%uq%u",stage_,
        static_cast<unsigned>(result.outcome),static_cast<unsigned>(dispatched_),
        static_cast<unsigned>(result.entry),static_cast<unsigned>((result.history&wire::outbound_queued)!=0));
    if(length<0 || static_cast<std::size_t>(length)>=result.detail.size()) { result.detail={}; }
    return result;
}
Operation NativeTarget::Prepare(const movement::NativeScene& scene,const wire::Command& command,
    Admission current,Admission append_current,void* context) noexcept {
    if(!Available() || !Owner() || running_ || actor_ || target_ || request_ || transfer_
        || !current || !append_current) { return {O::unavailable}; }
    scene_=scene; command_=command; current_=current; append_current_=append_current; context_=context;
    preparing_=running_=true; dispatched_=false; submission_receipt_={}; power_receipt_={};
    auto result=Guarded(); running_=preparing_=false; return result;
}
Operation NativeTarget::Execute(const wire::Command& command) noexcept {
    if(!Prepared() || !Owner() || running_ || request_ || transfer_ || !wire::SameEngagement(command_,command)
        || command.action==wire::Action::none || !wire::Valid(command.action,command.power_id,wire::Verb::submit)) {
        return {O::unavailable,wire::Entry::never_entered};
    }
    command_=command; running_=true; dispatched_=false; submission_receipt_={}; power_receipt_={};
    auto result=Guarded(); running_=false;
    // Nonfaulted interrupted pre-send ownership remains ours and is consumed once.
    if(!faulted_ && (request_ || transfer_)) {
        running_=true;
        __try { (void)ClearMessagesCxx(); } __except(EXCEPTION_EXECUTE_HANDLER) { faulted_=true; }
        running_=false;
        if(faulted_) { result.outcome=O::uncertain; result.history|=wire::uncertain_history; }
    }
    return result;
}
bool NativeTarget::ReadState(const movement::NativeScene& scene,Observation& out) const noexcept {
    std::uintptr_t table{},pointer{},after{}; std::array<std::uint32_t,2> key{};
    Observation first{},second{};
    auto read=[&](Observation& value) noexcept {
        return Read(pointer+0x18,value.mode) && Read(pointer+0x20,value.action)
            && Read(scene.actor+0x9bc,value.animation_event_index)
            && initiation::Capture(scene.actor,pointer,value.initiation,[](std::uintptr_t at, auto& value) noexcept { return Read(at,value); })
            && Read(scene.actor+0xaf8,value.target)
            && (!value.target || (value.target>=0x10000 && value.target<=0x7fff0000-4 && value.target%4==0));
    };
    if(!Owner() || !movement::NativeMovementLifetimeCurrent(scene) || !Read(base_+0x16a2d98,after) || after!=scene.actor
        || !Read(scene.actor,table) || table!=base_+0x114165c || !Read(scene.actor+0x18,key) || key!=scene.identity
        || !Read(scene.actor+0xad0,pointer) || pointer<0x10000 || pointer%4
        || !read(first) || !read(second) || first!=second || !Read(scene.actor+0xad0,after) || pointer!=after
        || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
    out=first; return true;
}
bool NativeTarget::CombatTargetCurrent() const noexcept {
    Observation state{}; return Prepared() && ReadState(scene_,state) && state.target==reinterpret_cast<std::uintptr_t>(target_);
}
bool NativeTarget::CancelImpl(const movement::NativeScene& scene,Admission current,void* context,Observation& out) {
    if(power::NativeUseInFlight() || !current || !current(context) || !ReadState(scene,out)) { return false; }
    if(out.mode==2) {
        const std::array<std::uint32_t,9> action{0x616};
        if(!current(context) || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
        (void)calls_.dispatch(action.data(),reinterpret_cast<void*>(scene.window));
    }
    return current(context) && ReadState(scene,out) && out.mode==1 && out.ClearInitiation() && !out.target;
}
bool NativeTarget::CancelCxx(const movement::NativeScene& scene,Admission current,void* context,Observation& state) noexcept {
    try { return CancelImpl(scene,current,context,state); }
    catch(...) { faulted_=true; return false; }
}
bool NativeTarget::Cancel(const movement::NativeScene& scene,Admission current,void* context,Observation& state) noexcept {
    if(!Available() || !Owner() || running_) { return false; }
    running_=true; bool result=false;
    __try { result=CancelCxx(scene,current,context,state); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_=true; }
    running_=false; return result;
}
}
