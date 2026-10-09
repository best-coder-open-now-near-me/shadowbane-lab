#include "actor_action_runtime.cpp"
#include "actor_publication.cpp"
#undef NDEBUG
#include <cassert>
#include <cstdio>

namespace a=wonderbane::extension::actor;
namespace w=a::wire;
namespace f=a::fence;
namespace m=wonderbane::extension::movement;
namespace outer=wonderbane::extension::combat;
namespace b=wonderbane::extension::actor_buffs;
namespace ac=wonderbane::extension::combat::activation;
namespace {
ac::ActivationHistory activation_history;
unsigned checks{},calls{},stops{},child_stops{},begins{},pauses{},released{},revalidations{};
bool live=true,read_scene=true,lease_live=true,stop_ok=true,native_activity=false,defer_child=false,poll_settled=false;
unsigned fail_revalidation{},continuation_checks{};
bool continuation_current=true,item_effect_present=false,power_effect_present=false,preparation_idle=true,preparation_owner_available=true;
std::uint64_t preparation_epoch=1,item_deadline{},item_second_deadline{};std::uint32_t item_remaining{};
m::NativeScene fixture_scene{0x10000,0x20000,0x30000,0x40000,{91,53},7};
m::Grant owner{9,7,m::Owner::automation};
void Check(bool value,const char* label){++checks;if(!value){std::fprintf(stderr,"FAILED: %s\n",label);std::abort();}}
w::Id Id(unsigned n){w::Id id{};for(unsigned i=0;i<4;++i){id[15-i]=static_cast<std::uint8_t>(n>>(i*8));}return id;}
bool Validate(void*,const m::wire::Host&,std::uint64_t)noexcept{return lease_live;}
template<class Binding>struct Mapping {
    HANDLE handle{},mutex{};Binding* view{};
    explicit Mapping(Binding binding){
        const auto name=f::Name(binding);Check(!name.empty(),"canonical fence name");
        mutex=CreateMutexW(nullptr,FALSE,(name+L".lock").c_str());
        handle=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Binding),name.c_str());
        Check(mutex&&handle&&GetLastError()!=ERROR_ALREADY_EXISTS,"fresh actual fence mapping");
        view=static_cast<Binding*>(MapViewOfFile(handle,FILE_MAP_ALL_ACCESS,0,0,sizeof(Binding)));Check(view!=nullptr,"fence mapped");
        binding.state=f::State::pending;*view=binding;
    }
    ~Mapping(){if(view){UnmapViewOfFile(view);}if(handle){CloseHandle(handle);}if(mutex){CloseHandle(mutex);}}
};
struct ManifestMapping {
    HANDLE handle{};void* view{};w::Digest digest{};
    explicit ManifestMapping(const a::selectors::Manifest& manifest){
        Check(a::selectors::Hash(manifest,digest),"qualified selector manifest");const auto name=a::selectors::Name(digest);
        handle=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(manifest),name.c_str());
        Check(handle&&GetLastError()!=ERROR_ALREADY_EXISTS,"fresh selector mapping");
        view=MapViewOfFile(handle,FILE_MAP_ALL_ACCESS,0,0,sizeof(manifest));Check(view!=nullptr,"selector mapping view");std::memcpy(view,&manifest,sizeof(manifest));
    }
    ~ManifestMapping(){if(view){UnmapViewOfFile(view);}if(handle){CloseHandle(handle);}}
};
w::Command Base(){w::Command c{};c.host={GetCurrentProcessId(),1,f::Creation(GetCurrentProcess())};c.window=0x50000;c.request=Id(1);return c;}
w::Command Parent(unsigned id,f::ActorBinding& binding){
    auto c=Base();c.grant=m::wire::Encode(owner);c.parent_id=Id(id);
    binding={};binding.client_pid=binding.producer_pid=GetCurrentProcessId();binding.client_creation=binding.producer_creation=c.host.creation;
    binding.producer_generation=1;binding.movement_generation=owner.generation;binding.scene=owner.scene;
    binding.owner_id=c.parent_id;binding.actor_key[0]=fixture_scene.identity[0];binding.actor_key[1]=53;binding.actor_hint=static_cast<std::uint32_t>(fixture_scene.actor);
    binding.local_name.fill(1);binding.server.fill(2);binding.owner.fill(3);
    Check(f::Hash(&c.grant.token,sizeof(c.grant.token),binding.operation)&&f::HashBinding(binding,c.parent_digest),"parent grant bound digest");return c;
}
w::Command Child(const w::Command& parent,unsigned id,f::ContextBinding& binding){
    auto c=parent;c.context_id=Id(id);binding={};binding.parent_digest=parent.parent_digest;binding.context_id=c.context_id;
    binding.authority=2;binding.target_hint=0x60000+id*4;binding.target_key[0]=92+id;binding.target_key[1]=37;
    Check(f::HashBinding(binding,c.context_digest),"child exact target digest");return c;
}
a::selectors::Manifest Manifest(){
    a::selectors::Manifest value;value.client_pid=value.producer_pid=GetCurrentProcessId();
    value.client_creation=value.producer_creation=f::Creation(GetCurrentProcess());value.producer_generation=1;
    value.local_name.fill(1);value.server.fill(2);value.count=value.groups=2;
    value.records[0]={0,0,4,0,980066,0,429021400,0};value.records[1]={1,1,3,111,0,0,111,0};return value;
}
w::Receipt Execute(w::Verb verb,const w::Command& input){
    Check(w::Valid(verb,input),"test command wire valid");auto command=std::make_shared<a::QueuedCommand>();command->command=input;command->verb=verb;
    command->deadline=GetTickCount64()+10000;command->lease=std::make_shared<m::CommandLease>();command->lease->host=input.host;
    command->lease->process=OpenProcess(SYNCHRONIZE,FALSE,GetCurrentProcessId());command->lease->validate=Validate;
    Check(command->lease->process&&a::Queue(command),"real producer lease and queued command");
    a::runtime.Tick(reinterpret_cast<void*>(fixture_scene.window),reinterpret_cast<HWND>(input.window));
    Check(command->state.load()==2,"owner service completed command");const auto result=command->receipt;
    Check(w::Correlated(input,verb,result),"correlated production receipt");a::Release(command);return result;
}
void Tick(){a::runtime.Tick(reinterpret_cast<void*>(fixture_scene.window),reinterpret_cast<HWND>(0x50000));}
void StartActivation(const ac::Handle& handle){
    const auto record=activation_history.Read(handle.slot);
    const auto state=activation_history.BeginStart(handle.identity,record.power,1,2,3,GetCurrentThreadId());
    Check(state&&activation_history.StateReturned(state,true),"fixture exact incoming state transition");
    const auto append=activation_history.BeginAppend(handle.identity,record.power,1,2,3,GetCurrentThreadId());
    Check(append&&activation_history.AppendReturned(append,true)&&activation_history.StartProcessReturned(append,true),"fixture incoming append and normal Process return");
}
void InterruptActivation(const ac::Handle& handle){
    StartActivation(handle);const auto movement=activation_history.BeginMovement(handle.identity);
    Check(movement&&activation_history.MovementReturned(movement,true),"fixture exact movement transition");
}
w::Command Buff(const w::Command& parent,unsigned request,unsigned selector){
    auto command=parent;command.request=Id(request);command.recipient=w::Recipient::actor;command.selector_index=selector;
    command.manifest_digest=a::runtime.manifest_digest;a::publication::Frame frame{};Check(a::runtime.publisher.Current(frame)&&frame.complete,"current publication available for action");
    command.publication_revision=frame.revision;command.snapshot_id=frame.snapshot;
    if(selector==0){command.action=w::Action::use_item;command.item_key[0]=55;command.item_key[1]=30;
        command.template_key[0]=980066;command.item_hint=0x70000;command.template_hint=0x80000;}
    else{command.action=w::Action::self_power;command.power_id=111;}return command;
}
}
namespace wonderbane::extension::movement {
bool VerifyNativeMovementImage(std::uintptr_t& image)noexcept{image=0x400000;return true;}
bool NativeMovementLifetimeCurrent(const NativeScene& scene)noexcept{return live&&scene.epoch==fixture_scene.epoch;}
bool ReadNativeMovementLifetime(NativeScene& scene)noexcept{scene=fixture_scene;return live&&read_scene;}
bool NativePreparationEntryCurrent(const NativeScene& scene,std::uint64_t& epoch)noexcept{epoch=preparation_epoch;return preparation_idle&&NativeMovementLifetimeCurrent(scene);}
bool NativePreparationOwnerAvailable(const NativeScene& scene)noexcept{return preparation_owner_available&&NativeMovementLifetimeCurrent(scene);}
bool NativePreparationUninterrupted(const NativeScene& scene,std::uint64_t epoch)noexcept{return epoch==preparation_epoch&&NativeMovementLifetimeCurrent(scene);}
bool NativeOwnerActionCurrent(const NativeScene& scene,const Grant& grant,const wire::Host&)noexcept{return NativeMovementLifetimeCurrent(scene)&&grant==owner&&lease_live;}
bool NativeOwnerStopCurrent(const NativeScene& scene,const Grant& grant)noexcept{return NativeMovementLifetimeCurrent(scene)&&grant==owner;}
Result BeginNativeOwnerAction(const NativeScene& scene,const Grant& grant,const wire::Host& host)noexcept{
    if(!NativeOwnerActionCurrent(scene,grant,host)){return Result::stale;}++begins;native_activity=true;return Result::accepted;
}
Result PauseNativeOwnerAction(const NativeScene& scene,const Grant& grant)noexcept{
    ++pauses;if(!NativeOwnerStopCurrent(scene,grant)){return Result::stale;}
    if(native_activity&&!combat_owner_stop.load()(scene,grant,StopReason::release)){return Result::stop_failed;}
    native_activity=false;return Result::accepted;
}
}
namespace wonderbane::extension::combat::submission {bool Start(std::uintptr_t)noexcept{return true;}bool Ready()noexcept{return true;}}
namespace wonderbane::extension::combat::power {bool Start(std::uintptr_t)noexcept{return true;}bool Ready()noexcept{return true;}}
namespace wonderbane::extension::combat::activation {
Handle Arm(std::size_t slot,const ActivationIdentity& identity,std::uint32_t power,ActivationOrigin origin)noexcept{
    return {slot,activation_history.Arm(slot,identity,power,origin),identity};
}
void RecordReturn(const Handle& h,bool queued,bool followup)noexcept{
    activation_history.QueueResult(h.slot,h.ticket,queued);activation_history.OwnedFollowup(h.slot,h.ticket,followup);
}
Result Read(const Handle& h)noexcept{
    const auto record=activation_history.Read(h.slot);
    if(!h||record.ticket!=h.ticket||record.identity!=h.identity){return Result::unknown;}
    if(record.phase==ActivationPhase::interrupted){return Result::interrupted;}
    if(record.phase==ActivationPhase::completed){return Result::completed;}
    if(record.local_relinquished){return Result::relinquished;}
    return Result::awaiting;
}
bool ResetExactLifetime(const ActivationIdentity& identity)noexcept{return activation_history.ResetExactLifetime(identity);}
}
namespace wonderbane::extension::combat::item {bool Start(std::uintptr_t)noexcept{return true;}}
namespace wonderbane::extension::combat::inventory {bool Start(std::uintptr_t)noexcept{return true;}}
// The native gameplay backend is synthetic; copied effects still pass through
// the production publication encoder and application journal projection.
namespace wonderbane::extension::actor_buffs {
Unknown Capture(const actor_effects::Context&,const Request& request,State&,Publication& out)noexcept{
    out.effects_.count=0;
    for(std::uint32_t i=0;i<request.count;++i){if(request.actions[i].power_id?power_effect_present:item_effect_present){
        auto& effect=out.effects_.effects[out.effects_.count++];effect.descriptor_id=222+i;
        effect.action_id=333+i;effect.rank=35;effect.action_class=actor_effects::ActionClass::apply;
        if(!request.actions[i].power_id&&item_second_deadline){auto& second=out.effects_.effects[out.effects_.count++];
            second.descriptor_id=999;second.action_id=444;second.rank=35;second.action_class=actor_effects::ActionClass::apply;}
    }}return Unknown::none;
}
}
namespace wonderbane::extension::actor {
bool NativeActor::BindScene(const m::NativeScene& scene,HWND window,Admission current,void* owner_context)noexcept{
    scene_=scene;window_=window;scene_current_=current;scene_context_=owner_context;image_=0x400000;actor_=reinterpret_cast<void*>(scene.actor);return SceneCurrent();
}
bool NativeActor::Available()const noexcept{return image_&&actor_&&!faulted_;}
bool NativeActor::SceneCurrent()const noexcept{return Available()&&scene_current_&&scene_current_(scene_context_);}
bool NativeActor::MatchesIdentity(const wire::Digest&,const wire::Digest&)const noexcept{return SceneCurrent();}
bool NativeActor::ReleaseScene()noexcept{if(m::NativeMovementLifetimeCurrent(scene_)){return false;}++released;image_=0;actor_=nullptr;return true;}
bool NativeActor::ValidateParent(const fence::ActorBinding& binding,Gates gates)noexcept{
    if(!SceneCurrent()||!gates.current(gates.context)){return false;}parent_=binding;parent_gates_=gates;parent_bound_=true;revoked_=false;return true;
}
NativeActor::Operation NativeActor::Attach(const fence::ContextBinding& binding,Gates gates)noexcept{
    Operation result;if(!gates.current(gates.context)){return result;}
    if(defer_child){result.outcome=wire::Outcome::deferred;result.closure=wire::Closure::local_released;return result;}
    child_=binding;child_gates_=gates;child_bound_=true;result.outcome=wire::Outcome::bound;ReadState(result.state);return result;
}
NativeActor::Operation NativeActor::Submit(const wire::Command& command,combat::activation::Handle activation)noexcept{
    Check(parent_gates_.current(parent_gates_.context)&&parent_gates_.append_current(parent_gates_.context),"native backend sees exact admitted parent gates");
    if(wire::Any(command.context_id)){Check(child_gates_.current(child_gates_.context)&&child_gates_.append_current(child_gates_.context),"native backend sees exact admitted child gates");}
    ++calls;Operation result;result.outcome=wire::Outcome::queued;result.entry=wire::Entry::entered;result.history=wire::outbound_queued;
    if(command.action==wire::Action::self_power){result.local_settlement=wire::LocalSettlement::pending;pending_=true;pending_command_=command;pending_operation_=result;}
    combat::activation::RecordReturn(activation,true,command.action==wire::Action::self_power);
    ReadState(result.state);return result;
}
bool NativeActor::PendingCommand(wire::Command& out)const noexcept{if(!pending_){return false;}out=pending_command_;return true;}
NativeActor::Operation NativeActor::Poll()noexcept{
    auto result=pending_operation_;if(poll_settled){pending_=false;result.local_settlement=wire::LocalSettlement::settled;pending_operation_=result;}ReadState(result.state);return result;
}
bool NativeActor::ContinueContext()noexcept{
    ++continuation_checks;return child_bound_&&continuation_current&&SceneCurrent()
        &&child_gates_.current(child_gates_.context);
}
bool NativeActor::ReadAdmission(std::uint32_t& blocks)noexcept{blocks=pending_?admission::local_action:0;return SceneCurrent();}
bool NativeActor::ReadState(Observation& state)const noexcept{state={};state.mode=1;state.action_state=2;state.initiation.state=5;return live;}
NativeActor::Operation NativeActor::StopContext(const fence::ContextBinding& child,Admission gate,void* owner_context)noexcept{
    ++child_stops;Operation result;result.outcome=wire::Outcome::pending;result.local_settlement=wire::LocalSettlement::pending;
    if(child_bound_&&fence::Same(child_,child)&&gate(owner_context)&&stop_ok){child_bound_=false;result.outcome=wire::Outcome::closed;result.closure=wire::Closure::native_stopped;result.local_settlement=wire::LocalSettlement::settled;}
    ReadState(result.state);return result;
}
NativeActor::Operation NativeActor::StopOwner(const fence::ActorBinding&,Admission gate,void* owner_context)noexcept{
    ++stops;Operation result;result.outcome=wire::Outcome::pending;result.local_settlement=wire::LocalSettlement::pending;
    if(gate(owner_context)&&stop_ok&&!(parent_.purpose==fence::Purpose::preparation&&pending_)){parent_bound_=child_bound_=pending_=false;result.outcome=wire::Outcome::closed;result.closure=parent_.purpose==fence::Purpose::preparation?wire::Closure::local_released:wire::Closure::native_stopped;result.local_settlement=wire::LocalSettlement::settled;}
    ReadState(result.state);return result;
}
void NativeActor::Revoke()noexcept{revoked_=true;}
b::Unknown NativeActor::Publish(const b::Request& request,b::Publication& out)noexcept{
    revalidations=0;out={};if(!SceneCurrent()){return b::Unknown::identity;}out.unknown=b::Unknown::none;
    out.actor_key=scene_.identity;out.scene=scene_.epoch;out.effect_epoch=1;out.count=request.count;out.actor_mode=1;out.initiation_clear=!pending_;out.admission_blocks=pending_?admission::local_action:0;
    for(std::uint32_t i=0;i<out.count;++i){auto& fact=out.actions[i];fact.intent=request.actions[i];fact.learned_rank=fact.intent.power_id?40:0;
        fact.target_mode=2;fact.required_mode=3;fact.descriptor_count=1;fact.descriptors[0]={222+i,333+i,actor_effects::ActionClass::apply,0,false};
        fact.descriptors[0].present=fact.intent.power_id?power_effect_present:item_effect_present;
        fact.coverage=fact.descriptors[0].present?b::Coverage::present:b::Coverage::missing;fact.readiness=pending_?b::Readiness::initiation_pending:b::Readiness::ready;
        if(!fact.intent.power_id&&fact.coverage==b::Coverage::present){fact.deadline_stamp=item_deadline;fact.remaining_ms=item_remaining;fact.descriptors[0].deadline_stamp=item_deadline;fact.descriptors[0].remaining_ms=item_remaining;
            if(item_second_deadline){fact.descriptor_count=2;fact.descriptors[1]={999,444,actor_effects::ActionClass::apply,0,true,item_second_deadline,item_remaining};
                if(item_second_deadline<fact.deadline_stamp){fact.deadline_stamp=item_second_deadline;}}
        }
        if(!fact.intent.power_id){fact.item_key={55,30};fact.item_template={980066,0};fact.item_hint=0x70000;fact.template_hint=0x80000;fact.item_quantity=3;fact.item_type=8;fact.item_flags=10;}
    }(void)b::Capture({},request,observation_state_,out);publication_=out;return b::Unknown::none;
}
bool NativeActor::RevalidatePublication(const b::Publication& value)noexcept{return SceneCurrent()&&value.Complete()&&++revalidations!=fail_revalidation;}
}
int main(){
    owner.token.worker[0]='w';owner.token.operation[0]='o';Check(outer::Start({GetCurrentProcessId(),f::Creation(GetCurrentProcess())}),"runtime registers native service");Tick();Check(outer::Ready(),"scene bound outside parent lifetime");
    auto manifest=Manifest();ManifestMapping source(manifest);auto read=Base();read.selector_index=0;read.manifest_digest=source.digest;
    Check(Execute(w::Verb::register_selectors,read).outcome==w::Outcome::observed,"native selector registration and publication");
    a::publication::Frame frame{};Check(a::runtime.publisher.Current(frame)&&frame.complete,"initial complete canonical publication");
    fail_revalidation=2;Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::unavailable,"final canonical revalidation failure surfaced");
    Check(a::runtime.publisher.Current(frame)&&!frame.complete,"failed final refresh replaces prior factual authority");fail_revalidation=0;
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"fresh accepted capture restores authority");
    const auto lifetime_before=a::runtime.actor_lifetime;
    read_scene=false;Tick();
    Check(!a::runtime.ready.load()&&!a::runtime.retired&&a::runtime.has_manifest&&released==0
        &&a::runtime.actor_lifetime==lifetime_before,"transient scene read failure blocks readiness without retiring retained actor");
    read_scene=true;Tick();Check(a::runtime.ready.load()&&a::runtime.actor_lifetime==lifetime_before,"fresh scene read resumes the same lifetime");
    f::ActorBinding parent_binding{};auto parent=Parent(1,parent_binding);Mapping parent_map(parent_binding);
    Check(Execute(w::Verb::open_owner,parent).outcome==w::Outcome::bound&&begins==1&&pauses==0,"open parent without blanket pause");
    auto item=Buff(parent,1,0);
    const auto eligibility_before=a::runtime.publisher.AdmissionRevision();
    auto stale=item;stale.request=Id(1);stale.snapshot_id[0]^=1;
    // Call the production invoker directly: transport/controller rejection is not the predicate under test.
    a::runtime.updating=true;
    for(unsigned i=0;i<3;++i){auto refused=a::runtime.Submit(stale);
        Check(refused.outcome==w::Outcome::deferred&&refused.reason==w::Reason::observation,
            "stale command snapshot is protocol refusal only");}
    a::runtime.updating=false;
    Check(a::runtime.publisher.AdmissionRevision()==eligibility_before,"stale requests cannot manufacture admission progress");
    auto result=Execute(w::Verb::submit,item);
    Check(result.outcome==w::Outcome::queued&&result.application==w::Application::pending&&result.local_settlement==w::LocalSettlement::settled&&calls==1,"item remote pending does not retain local initiation");
    (void)Execute(w::Verb::submit,item);Check(calls==1,"immutable action replay never repeats item");
    auto duplicate=Buff(parent,2,0);Check(Execute(w::Verb::submit,duplicate).outcome==w::Outcome::deferred&&calls==1,"same pending semantic group cannot reapply");
    auto power=Buff(parent,3,1);result=Execute(w::Verb::submit,power);
    Check(result.outcome==w::Outcome::queued&&result.local_settlement==w::LocalSettlement::pending&&calls==2&&pauses==0,"independent buff admitted during remote potion pending");
    auto blocked=Buff(parent,4,0);Check(Execute(w::Verb::submit,blocked).outcome==w::Outcome::deferred&&calls==2,"local initiation blocks fresh actions");
    item_effect_present=true;Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,
        "fresh native item coverage is published during independent local initiation");
    result=Execute(w::Verb::action_status,item);
    Check(result.application==w::Application::observed&&result.local_settlement==w::LocalSettlement::settled
        &&(result.flags&w::outbound_queued)&&!(result.flags&w::application_pending),
        "exact queued item digest projects observed application into immutable action status");
    result=Execute(w::Verb::action_status,power);
    Check(result.application==w::Application::pending&&result.local_settlement==w::LocalSettlement::pending
        &&a::runtime.journal.LocalPending()&&calls==2,
        "another action remains locally pending despite item effect presence");
    poll_settled=true;Tick();result=Execute(w::Verb::action_status,power);
    Check(result.local_settlement==w::LocalSettlement::settled&&result.application==w::Application::pending,"positive local poll does not invent remote effect");
    f::ContextBinding child_binding{};auto child=Child(parent,1,child_binding);Mapping child_map(child_binding);
    Check(Execute(w::Verb::attach_context,child).outcome==w::Outcome::bound&&pauses==0,"target attaches to existing actor owner without cancelling preparation");
    auto attack=child;attack.request=Id(5);attack.action=w::Action::attack;attack.recipient=w::Recipient::target;
    Check(Execute(w::Verb::submit,attack).outcome==w::Outcome::queued&&calls==3,"target action under parent admitted");
    const auto checks_before=continuation_checks;continuation_current=false;stop_ok=false;Tick();
    result=Execute(w::Verb::context_status,child);
    Check(result.context_phase==w::Phase::stopping&&result.owner_phase==w::Phase::bound,
        "failed continuation cleanup retains child obligation under parent");
    item_effect_present=false;Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,
        "fresh missing item coverage cannot erase child cleanup obligation");
    Check(a::runtime.publisher.Current(frame)&&(frame.admission_blocks&a::admission::child_cleanup),
        "publication exposes unresolved child cleanup without discarding effects");
    auto during_cleanup=Buff(parent,6,0);result=Execute(w::Verb::submit,during_cleanup);
    Check(result.entry==w::Entry::never_entered&&calls==3,
        "unconfirmed child cleanup blocks parent-only application as well as target action");
    stop_ok=true;Tick();
    Check(continuation_checks>checks_before,"settled ATTACK still validates native context continuation");
    result=Execute(w::Verb::context_status,child);continuation_current=true;
    Check(result.context_phase==w::Phase::closed&&result.owner_phase==w::Phase::bound&&a::runtime.active&&native_activity&&pauses==0,"invalidated settled target triggers child cleanup while preserving parent ownership");
    Check(Execute(w::Verb::action_status,item).application==w::Application::observed,"child closure preserves observed item application history");
    result=Execute(w::Verb::submit,during_cleanup);
    Check(result.outcome==w::Outcome::deferred&&result.entry==w::Entry::never_entered&&calls==3,
        "exact deferred replay remains immutable after child cleanup");
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,
        "fresh parent publication is available after child cleanup");
    Check(a::runtime.publisher.Current(frame)&&!frame.admission_blocks,
        "positive child cleanup clears local admission while remote applications remain pending");
    auto after_cleanup=Buff(parent,7,0);result=Execute(w::Verb::submit,after_cleanup);
    Check(result.outcome==w::Outcome::queued&&result.entry==w::Entry::entered&&calls==4,
        "positive child cleanup permits a fresh parent-only action");
    f::ContextBinding next_binding{};auto next=Child(parent,2,next_binding);Mapping next_map(next_binding);defer_child=true;const auto stopped_before=child_stops;
    result=Execute(w::Verb::attach_context,next);
    Check(result.closure==w::Closure::never_bound&&result.context_phase==w::Phase::closed&&child_stops==stopped_before,"positively released no-entry attach creates never-bound tombstone");defer_child=false;
    parent_map.view->state=f::State::entered_revoked;stop_ok=false;result=Execute(w::Verb::stop_owner,parent);
    Check(result.owner_phase==w::Phase::stopping&&a::runtime.active&&native_activity,"revoked fence does not abandon unresolved exact cleanup");
    auto wrong_owner=owner;++wrong_owner.generation;auto wrong_scene=fixture_scene;++wrong_scene.epoch;
    Check(!a::Runtime::StopOwner(fixture_scene,wrong_owner,m::StopReason::release)
        &&!a::Runtime::StopOwner(wrong_scene,owner,m::StopReason::release)&&a::runtime.active,
        "foreign owner or scene callback cannot close exact retained owner");
    stop_ok=true;Check(!a::runtime.updating,"cleanup callback starts outside actor Tick");
    Check(m::PauseNativeOwnerAction(fixture_scene,owner)==m::Result::accepted,
        "movement owner callback settles native cleanup outside actor Tick");
    result=Execute(w::Verb::owner_status,parent);Check(result.owner_phase==w::Phase::closed&&!a::runtime.active&&!native_activity,"exact cleanup callback publishes truthful closure after revocation");
    Check(Execute(w::Verb::action_status,power).application==w::Application::pending,"owner close preserves independent remote pending journal");
    Check(!wonderbane::extension::PreparationBlocksAutomation(),
        "remote application alone never manufactures preparation ownership");
    auto incompatible=manifest;incompatible.count=incompatible.groups=1;incompatible.records[0]=manifest.records[0];incompatible.records[0].index=incompatible.records[0].group=0;incompatible.records[1]={};
    ManifestMapping incompatible_map(incompatible);auto change=read;change.manifest_digest=incompatible_map.digest;
    Check(Execute(w::Verb::register_selectors,change).outcome==w::Outcome::deferred,"pending group cannot disappear through manifest replacement");
    auto compatible=manifest;std::swap(compatible.records[0],compatible.records[1]);compatible.records[0].index=0;compatible.records[1].index=1;
    ManifestMapping compatible_map(compatible);change.manifest_digest=compatible_map.digest;
    const auto floor=a::runtime.publisher.Revision();Check(Execute(w::Verb::register_selectors,change).outcome==w::Outcome::observed,"reordered canonical groups preserve pending history");
    Check(a::runtime.publisher.Current(frame)&&frame.revision>floor&&frame.application_count==2,"manifest migration keeps history and revision high-water");
    live=false;Tick();Check(released==1&&!a::runtime.has_manifest&&!a::runtime.journal.LocalPending(),"confirmed actor retirement releases publication and lifetime journal");

    live=true;++fixture_scene.epoch;owner.scene=fixture_scene.epoch;poll_settled=false;Tick();
    Check(Execute(w::Verb::register_selectors,read).outcome==w::Outcome::observed,"new exact scene publishes canonical maintenance facts");
    f::ActorBinding blocked_binding{};auto blocked_preparation=Parent(2,blocked_binding);
    blocked_binding.purpose=f::Purpose::preparation;blocked_binding.movement_generation=0;blocked_preparation.grant={};
    Check(f::Hash(blocked_binding.owner_id.data(),blocked_binding.owner_id.size(),blocked_binding.operation)
        &&f::HashBinding(blocked_binding,blocked_preparation.parent_digest),"blocked preparation exact binding");
    Mapping blocked_map(blocked_binding);preparation_owner_available=false;
    Check(Execute(w::Verb::open_owner,blocked_preparation).outcome!=w::Outcome::bound
        &&!wonderbane::extension::PreparationBlocksAutomation(),"existing movement owner prevents preparation open without seizing actor arbiter");
    preparation_owner_available=true;preparation_idle=false;
    f::ActorBinding preparation_binding{};auto preparation=Parent(3,preparation_binding);
    preparation_binding.purpose=f::Purpose::preparation;preparation_binding.movement_generation=0;preparation.grant={};
    Check(f::Hash(preparation_binding.owner_id.data(),preparation_binding.owner_id.size(),preparation_binding.operation)
        &&f::HashBinding(preparation_binding,preparation.parent_digest),"purpose-scoped immutable operation");
    Mapping preparation_map(preparation_binding);const auto before_begins=begins,before_pauses=pauses,before_calls=calls;
    Check(Execute(w::Verb::open_owner,preparation).outcome==w::Outcome::bound
        &&begins==before_begins&&wonderbane::extension::PreparationBlocksAutomation(),
        "preparation owns only actor arbiter, never acquires movement");
    auto forbidden=preparation;forbidden.context_id=Id(7);forbidden.context_digest.fill(1);
    Check(!w::Valid(w::Verb::attach_context,forbidden),"preparation cannot attach a target");
    forbidden=preparation;forbidden.action=w::Action::attack;forbidden.recipient=w::Recipient::target;
    Check(!w::Valid(w::Verb::submit,forbidden),"preparation cannot attack without combat authority");
    preparation_idle=false;++preparation_epoch;
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed&&a::runtime.publisher.Current(frame)
        &&(frame.admission_blocks&a::admission::manual_activity),"manual activity is entry veto, not lifetime loss");
    auto deferred=Buff(preparation,20,1);auto no_entry=Execute(w::Verb::submit,deferred);
    Check(no_entry.outcome==w::Outcome::deferred&&no_entry.reason==w::Reason::manual_activity
        &&no_entry.entry==w::Entry::never_entered&&calls==before_calls,"manual activity defers before native entry");
    preparation_idle=true;
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"fresh native idle permits re-admission");
    auto maintenance=Buff(preparation,21,1);Check(Execute(w::Verb::submit,maintenance).local_settlement==w::LocalSettlement::pending
        &&calls==before_calls+1,"background purpose enters exactly one qualified buff");
    preparation_idle=false;++preparation_epoch;
    Check(Execute(w::Verb::action_status,maintenance).local_settlement==w::LocalSettlement::pending,
        "manual entry suspension retains immutable status responsibility");
    auto closing=preparation;closing.request=Id(22);
    Check(Execute(w::Verb::stop_owner,closing).owner_phase==w::Phase::stopping
        &&wonderbane::extension::PreparationBlocksAutomation()&&pauses==before_pauses,
        "passive preparation close preserves unresolved local ownership without movement stop");
    poll_settled=true;Tick();const auto closed=Execute(w::Verb::owner_status,closing);
    Check(closed.owner_phase==w::Phase::closed&&closed.closure==w::Closure::local_released
        &&!wonderbane::extension::PreparationBlocksAutomation()&&pauses==before_pauses,
        "exact late local settlement releases arbiter without combat-off");
    const auto maintenance_slot=a::runtime.JournalIndex(maintenance);
    InterruptActivation(a::runtime.activations[maintenance_slot]);
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"closed parent retains canonical lifecycle observation");
    const auto ended=Execute(w::Verb::action_status,maintenance);
    Check(ended.application==w::Application::interrupted&&ended.local_settlement==w::LocalSettlement::settled
        &&ended.entry==w::Entry::entered&&(ended.flags&w::outbound_queued),"exact old command interruption retained after parent closure");
    Check(a::runtime.publisher.Current(frame)&&frame.applications[0].state==3
        &&frame.applications[0].observed_revision>frame.applications[0].submitted_revision
        &&frame.applications[0].observed_revision<=frame.revision,"published terminal observation has truthful fresh revision");
    f::ActorBinding resumed_binding{};auto resumed=Parent(4,resumed_binding);
    resumed_binding.purpose=f::Purpose::preparation;resumed_binding.movement_generation=0;resumed.grant={};
    Check(f::Hash(resumed_binding.owner_id.data(),resumed_binding.owner_id.size(),resumed_binding.operation)
        &&f::HashBinding(resumed_binding,resumed.parent_digest),"resumed preparation exact binding");
    Mapping resumed_map(resumed_binding);preparation_idle=true;
    Check(Execute(w::Verb::open_owner,resumed).outcome==w::Outcome::bound,"later parent preserves journal but can resume fresh missing coverage");
    for(unsigned cycle=0;cycle<3;++cycle){
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"fresh native stationary missing coverage");
        auto potion=Buff(resumed,40+cycle,0);const auto before=calls;
        Check(Execute(w::Verb::submit,potion).outcome==w::Outcome::queued&&calls==before+1,"one ordinary item entry for each fresh generation");
        const auto slot=a::runtime.JournalIndex(potion);const auto handle=a::runtime.activations[slot];
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,potion).application==w::Application::pending,"old terminal record does not clear newer same-group pending use");
        InterruptActivation(handle);Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"new generation interrupted");
        Check(Execute(w::Verb::action_status,potion).application==w::Application::interrupted&&calls==before+1,"status resolves exact original application without replay");
    }
    auto relinquished=Buff(resumed,50,1);
    Check(Execute(w::Verb::submit,relinquished).local_settlement==w::LocalSettlement::pending,"fresh owned power has local responsibility");
    const auto relinquished_slot=a::runtime.JournalIndex(relinquished);const auto relinquished_handle=a::runtime.activations[relinquished_slot];
    activation_history.ManualSend(fixture_scene.actor,999);
    Check(activation_history.ManualDirectReturned(relinquished_handle.identity,999,true),"fixture positive newer manual control");
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"canonical observation after independent local control relinquishment");
    const auto relinquished_receipt=Execute(w::Verb::action_status,relinquished);
    Check(relinquished_receipt.application==w::Application::pending&&relinquished_receipt.local_settlement==w::LocalSettlement::settled,
        "manual takeover local release cannot imply application interruption or retry permission");
    power_effect_present=true;
    Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
        &&Execute(w::Verb::action_status,relinquished).application==w::Application::observed,
        "positive effect presence independently resolves unknown remote interpretation");
    for(unsigned cycle=0;cycle<2;++cycle){
        item_effect_present=power_effect_present=false;
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"ordinary later expiry is freshly observed");
        auto sequential_item=Buff(resumed,60+cycle*2,0);
        Check(Execute(w::Verb::submit,sequential_item).local_settlement==w::LocalSettlement::settled,"item transaction settles without claiming effect");
        StartActivation(a::runtime.activations[a::runtime.JournalIndex(sequential_item)]);
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"other configured group remains observable during item application");
        auto sequential_power=Buff(resumed,61+cycle*2,1);
        Check(Execute(w::Verb::submit,sequential_power).outcome==w::Outcome::queued,"ordinary sequential power proceeds without effect barrier");
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,sequential_item).application==w::Application::pending,
            "competing control activity never fabricates item interruption");
        item_effect_present=power_effect_present=true;
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,sequential_item).application==w::Application::observed
            &&Execute(w::Verb::action_status,sequential_power).application==w::Application::observed,
            "fresh native coverage reconciles each sequential group and permits next expiry cycle");
    }
    Check(Execute(w::Verb::stop_owner,resumed).closure==w::Closure::local_released,"interrupted item is not fabricated local ownership");
    {
        f::ActorBinding track_binding{};auto tracking_owner=Parent(90,track_binding);
        track_binding.purpose=f::Purpose::preparation;track_binding.movement_generation=0;tracking_owner.grant={};
        Check(f::Hash(track_binding.owner_id.data(),track_binding.owner_id.size(),track_binding.operation)
            &&f::HashBinding(track_binding,tracking_owner.parent_digest),"tracking-only preparation identity");
        Mapping track_map(track_binding);
        Check(Execute(w::Verb::open_owner,tracking_owner).outcome==w::Outcome::bound,"tracking-only actor parent opens");
        auto query=tracking_owner;query.request=Id(2);query.action=w::Action::track;
        query.power_id=429578587;query.recipient=w::Recipient::actor;
        const auto records=a::runtime.journal.Records();const auto has_manifest=a::runtime.has_manifest;
        a::runtime.has_manifest=false;
        const auto track_result=Execute(w::Verb::submit,query);
        Check(track_result.outcome==w::Outcome::queued&&track_result.entry==w::Entry::entered
            &&track_result.local_settlement==w::LocalSettlement::settled&&track_result.application==w::Application::none,
            "Track has no selector publication or application barrier");
        Check(!std::memcmp(&records,&a::runtime.journal.Records(),sizeof(records)),"Track never mutates buff journal");
        preparation_idle=false;query.request=Id(3);
        Check(Execute(w::Verb::submit,query).reason==w::Reason::manual_activity,"manual preparation veto remains");
        preparation_idle=true;a::runtime.has_manifest=has_manifest;
        Check(Execute(w::Verb::stop_owner,tracking_owner).closure==w::Closure::local_released,"query has no cast cleanup");
    }
    {
        f::ActorBinding renewal_binding{};auto renewal=Parent(100,renewal_binding);
        renewal_binding.purpose=f::Purpose::preparation;renewal_binding.movement_generation=0;renewal.grant={};
        Check(f::Hash(renewal_binding.owner_id.data(),renewal_binding.owner_id.size(),renewal_binding.operation)
            &&f::HashBinding(renewal_binding,renewal.parent_digest),"early renewal parent identity");
        Mapping renewal_map(renewal_binding);Check(Execute(w::Verb::open_owner,renewal).outcome==w::Outcome::bound,"early renewal same preparation owner");
        item_effect_present=true;item_deadline=std::bit_cast<std::uint64_t>(115.0);item_second_deadline=std::bit_cast<std::uint64_t>(120.0);item_remaining=15001;
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"covered timer captured before lead");
        Check(Execute(w::Verb::submit,Buff(renewal,2,0)).outcome==w::Outcome::deferred,"covered potion outside lead refuses");
        item_remaining=15000;Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"lead boundary refresh");
        auto refresh=Buff(renewal,3,0);const auto before=calls;
        Check(Execute(w::Verb::submit,refresh).outcome==w::Outcome::queued&&calls==before+1,"covered exact conc queues once at native lead");
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,refresh).application==w::Application::pending,"old PRESENT never confirms covered renewal");
        Check(Execute(w::Verb::submit,Buff(renewal,4,0)).outcome==w::Outcome::deferred&&calls==before+1,"old deadline cannot consume another potion");
        item_deadline=std::bit_cast<std::uint64_t>(215.0);item_remaining=115000;
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,refresh).application==w::Application::pending,"only first descriptor renewed remains pending");
        Check(Execute(w::Verb::submit,Buff(renewal,5,0)).outcome==w::Outcome::deferred&&calls==before+1,"partial deadline advancement cannot consume another potion");
        item_second_deadline=std::bit_cast<std::uint64_t>(220.0);
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,refresh).application==w::Application::observed,"advanced deadline confirms new coverage without missing frame");
        Check(Execute(w::Verb::submit,Buff(renewal,6,0)).outcome==w::Outcome::deferred,"renewed coverage outside lead suppresses duplicate");
        item_remaining=15000;Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed,"second natural lead reached");
        auto second=Buff(renewal,7,0);Check(Execute(w::Verb::submit,second).outcome==w::Outcome::queued,"second covered cycle can renew");
        item_deadline=std::bit_cast<std::uint64_t>(315.0);item_second_deadline=std::bit_cast<std::uint64_t>(320.0);item_remaining=115000;
        Check(Execute(w::Verb::observe_actor,read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,second).application==w::Application::observed,"second cycle exact application observed");
        auto alternatives=manifest;alternatives.records[1].group=0;alternatives.groups=1;
        ManifestMapping alternative_source(alternatives);auto alternative_read=read;alternative_read.manifest_digest=alternative_source.digest;
        item_remaining=15000;power_effect_present=true;
        Check(Execute(w::Verb::register_selectors,alternative_read).outcome==w::Outcome::observed,"same group alternatives published");
        Check(Execute(w::Verb::submit,Buff(renewal,8,0)).outcome==w::Outcome::deferred,"other covered alternative prevents Concoction renewal");
        power_effect_present=false;
        Check(Execute(w::Verb::observe_actor,alternative_read).outcome==w::Outcome::observed,"other alternative missing but Concoction covereddue");
        Check(Execute(w::Verb::submit,Buff(renewal,9,1)).outcome==w::Outcome::deferred,"missing other action cannot borrow covered Concoction renewal eligibility");
        auto third=Buff(renewal,10,0);
        Check(Execute(w::Verb::submit,third).outcome==w::Outcome::queued,"covered Concoction selected within mixed alternatives");
        power_effect_present=true;item_deadline=std::bit_cast<std::uint64_t>(415.0);
        item_second_deadline=std::bit_cast<std::uint64_t>(420.0);item_remaining=115000;
        Check(Execute(w::Verb::observe_actor,alternative_read).outcome==w::Outcome::observed
            &&Execute(w::Verb::action_status,third).application==w::Application::observed,"later untimed alternative does not obstruct exact Concoction descriptor advancement");
        Check(Execute(w::Verb::stop_owner,renewal).closure==w::Closure::local_released,"renewal remote evidence does not invent local obligation");
    }
    std::printf("actor runtime: %u checks, %u native submits, no failures\n",checks,calls);return 0;
}

namespace wonderbane::extension::item_trace {
void OwnedReturn(const actor::wire::Command&,const movement::NativeScene&,actor::wire::Outcome,
    actor::wire::Entry,actor::wire::LocalSettlement,std::uint32_t,const combat::power::Receipt*) noexcept {}
}
