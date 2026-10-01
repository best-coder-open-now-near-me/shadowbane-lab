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
namespace {
unsigned checks{},calls{},stops{},child_stops{},begins{},pauses{},released{},revalidations{};
bool live=true,read_scene=true,lease_live=true,stop_ok=true,native_activity=false,defer_child=false,poll_settled=false;
unsigned fail_revalidation{},continuation_checks{};
bool continuation_current=true,item_effect_present=false;
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
namespace wonderbane::extension::combat::item {bool Start(std::uintptr_t)noexcept{return true;}}
namespace wonderbane::extension::combat::inventory {bool Start(std::uintptr_t)noexcept{return true;}}
// The native gameplay backend is synthetic; copied effects still pass through
// the production publication encoder and application journal projection.
namespace wonderbane::extension::actor_buffs {
Unknown Capture(const actor_effects::Context&,const Request& request,State&,Publication& out)noexcept{
    out.effects_.count=0;
    for(std::uint32_t i=0;i<request.count;++i){if(item_effect_present&&!request.actions[i].power_id){
        auto& effect=out.effects_.effects[out.effects_.count++];effect.descriptor_id=222+i;
        effect.action_id=333+i;effect.rank=35;effect.action_class=actor_effects::ActionClass::apply;
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
NativeActor::Operation NativeActor::Submit(const wire::Command& command)noexcept{
    Check(parent_gates_.current(parent_gates_.context)&&parent_gates_.append_current(parent_gates_.context),"native backend sees exact admitted parent gates");
    if(wire::Any(command.context_id)){Check(child_gates_.current(child_gates_.context)&&child_gates_.append_current(child_gates_.context),"native backend sees exact admitted child gates");}
    ++calls;Operation result;result.outcome=wire::Outcome::queued;result.entry=wire::Entry::entered;result.history=wire::outbound_queued;
    if(command.action==wire::Action::self_power){result.local_settlement=wire::LocalSettlement::pending;pending_=true;pending_command_=command;pending_operation_=result;}
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
bool NativeActor::ReadState(Observation& state)const noexcept{state={};state.mode=1;state.action_state=2;state.initiation.state=5;return live;}
NativeActor::Operation NativeActor::StopContext(const fence::ContextBinding& child,Admission gate,void* owner_context)noexcept{
    ++child_stops;Operation result;result.outcome=wire::Outcome::pending;result.local_settlement=wire::LocalSettlement::pending;
    if(child_bound_&&fence::Same(child_,child)&&gate(owner_context)&&stop_ok){child_bound_=false;result.outcome=wire::Outcome::closed;result.closure=wire::Closure::native_stopped;result.local_settlement=wire::LocalSettlement::settled;}
    ReadState(result.state);return result;
}
NativeActor::Operation NativeActor::StopOwner(const fence::ActorBinding&,Admission gate,void* owner_context)noexcept{
    ++stops;Operation result;result.outcome=wire::Outcome::pending;result.local_settlement=wire::LocalSettlement::pending;
    if(gate(owner_context)&&stop_ok){parent_bound_=child_bound_=pending_=false;result.outcome=wire::Outcome::closed;result.closure=wire::Closure::native_stopped;result.local_settlement=wire::LocalSettlement::settled;}
    ReadState(result.state);return result;
}
void NativeActor::Revoke()noexcept{revoked_=true;}
b::Unknown NativeActor::Publish(const b::Request& request,b::Publication& out)noexcept{
    revalidations=0;out={};if(!SceneCurrent()){return b::Unknown::identity;}out.unknown=b::Unknown::none;
    out.actor_key=scene_.identity;out.scene=scene_.epoch;out.effect_epoch=1;out.count=request.count;out.actor_mode=1;out.initiation_clear=!pending_;
    for(std::uint32_t i=0;i<out.count;++i){auto& fact=out.actions[i];fact.intent=request.actions[i];fact.learned_rank=fact.intent.power_id?40:0;
        fact.target_mode=2;fact.required_mode=3;fact.descriptor_count=1;fact.descriptors[0]={222+i,333+i,actor_effects::ActionClass::apply,0,false};
        fact.descriptors[0].present=item_effect_present&&!fact.intent.power_id;
        fact.coverage=fact.descriptors[0].present?b::Coverage::present:b::Coverage::missing;fact.readiness=pending_?b::Readiness::initiation_pending:b::Readiness::ready;
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
    auto item=Buff(parent,1,0);auto result=Execute(w::Verb::submit,item);
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
    auto incompatible=manifest;incompatible.count=incompatible.groups=1;incompatible.records[0]=manifest.records[0];incompatible.records[0].index=incompatible.records[0].group=0;incompatible.records[1]={};
    ManifestMapping incompatible_map(incompatible);auto change=read;change.manifest_digest=incompatible_map.digest;
    Check(Execute(w::Verb::register_selectors,change).outcome==w::Outcome::deferred,"pending group cannot disappear through manifest replacement");
    auto compatible=manifest;std::swap(compatible.records[0],compatible.records[1]);compatible.records[0].index=0;compatible.records[1].index=1;
    ManifestMapping compatible_map(compatible);change.manifest_digest=compatible_map.digest;
    const auto floor=a::runtime.publisher.Revision();Check(Execute(w::Verb::register_selectors,change).outcome==w::Outcome::observed,"reordered canonical groups preserve pending history");
    Check(a::runtime.publisher.Current(frame)&&frame.revision>floor&&frame.application_count==2,"manifest migration keeps history and revision high-water");
    live=false;Tick();Check(released==1&&!a::runtime.has_manifest&&!a::runtime.journal.LocalPending(),"confirmed actor retirement releases publication and lifetime journal");
    std::printf("actor runtime: %u checks, %u native submits, no failures\n",checks,calls);return 0;
}
