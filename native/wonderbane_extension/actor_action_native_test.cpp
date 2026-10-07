#include "actor_action_native.h"
#include "combat_v2_wire.h"
#undef NDEBUG
#include <cassert>
#include <map>
#include <stdexcept>
#include <functional>
#include <utility>
namespace c= wonderbane::extension::combat::v2;
namespace m= wonderbane::extension::movement;
namespace s= wonderbane::extension::combat::submission;
namespace p= wonderbane::extension::combat::power;
namespace melee= wonderbane::extension::combat::melee;
using O=c::wire::Outcome;
namespace {
std::uintptr_t base{}; HWND window{}; m::NativeScene scene{};
bool live=true,admitted=true,throw_attack=false,seh_attack=false,reject_cancel=false;
unsigned attacks{},casts{},stops{},lookups{},restores{},lookup_mode{};
double initiation_seconds{};
std::uint32_t learned_rank=20, definition_generation=1;
bool definition_available=true; unsigned availability_change{};
std::uint64_t epoch=1;
bool mutate_after_definition=false, mutate_on_current=false;
bool native_in_flight=false, mutate_before_entry=false, mutate_after_entry=false;
std::function<void()> current_callback;
std::map<void*,unsigned> references;
s::Context melee_context{}; p::Context power_context{};
s::Receipt melee_receipt{s::Result::queued,true,true,true};
p::Receipt power_receipt{p::Result::queued,true,true,true,true};
template<class T> void Put(std::uintptr_t at,T value) { std::memcpy(reinterpret_cast<void*>(at),&value,sizeof(value)); }
bool Current(void*) noexcept { if(current_callback){auto callback=std::exchange(current_callback,{});callback();} if(mutate_on_current) { ++epoch; mutate_on_current=false; } return admitted; }
void Protocol(std::initializer_list<std::uint32_t> ids) {
    const auto storage=base+0xf000;
    std::size_t i=0; for(auto id:ids) { Put(storage+i++*4,id); }
    Put(scene.actor+0x65c,static_cast<std::uint32_t>(storage));
    Put(scene.actor+0x660,static_cast<std::uint32_t>(storage+ids.size()*4));
    Put(scene.actor+0x664,static_cast<std::uint32_t>(storage+256*4));
}
void Text(std::uintptr_t field,std::uintptr_t storage,const wchar_t* value) {
    const auto count=wcslen(value); std::memcpy(reinterpret_cast<void*>(storage),value,(count+1)*2);
    Put(field+4,storage); Put(field+8,storage+count*2); Put(field+12,storage+(count+1)*2);
}
void Reset() {
    for(const auto& [object,count]:references) { (void)object; assert(!count); }
    std::memset(reinterpret_cast<void*>(base),0,0x10000); references.clear(); lookup_mode=0;
    mutate_after_definition=mutate_on_current=false; native_in_flight=mutate_before_entry=mutate_after_entry=false; epoch=1; initiation_seconds=0; learned_rank=20; definition_generation=1; definition_available=true;
    availability_change=0; live=admitted=true; throw_attack=seh_attack=reject_cancel=false; attacks=casts=stops=lookups=0;
    melee_receipt={s::Result::queued,true,true,true}; power_receipt={p::Result::queued,true,true,true,true,1};
    scene={}; scene.epoch=1; scene.actor=base+0x2000; scene.window=base+0x1000;
    scene.world=base+0x6000; scene.parent=0; scene.identity={100,53};
    Put(base+0x16a2d98,scene.actor); Put(base+0x16a7bfc,scene.window); Put(base+0x1389028,scene.world);
    Put(base+0x16a2da4,std::uintptr_t{1}); // Selection is poisoned throughout every test.
    Put(base+0x16ab88c,base+0xa000); Put(base+0xa044,base+0xa100);
    Put(scene.window+0x98,base+0x8000); Put(base+0x809c,base+0x8100);
    Put(base+0x8100,base+0x8100); Put(base+0x8104,base+0x8100);
    Put(base+0x11416b4,base+0xa3d0);
    for(auto offset:{0x2000U,0x4000U}) {
        Put(base+offset,base+0x114165c); Put(base+offset+8,base+0x9000); Put(base+0x9004,std::int32_t{0x80});
        Put(base+offset+0x18,std::array<std::uint32_t,2>{offset==0x2000?100U:200U,53});
        Text(base+offset+0xc48,base+offset+0xd00,offset==0x2000?L"Local":L"Target");
        Text(base+offset+0xc90,base+offset+0xd80,L"Shard");
    }
    Put(scene.actor+0x4b0,base+0xb000); Put(base+0xb000,base+0xb100); Put(base+0xb108,scene.parent);
    Put(base+0xb120,m::GroundPoint{2000,40,-3000});
    Put(base+0xc010,std::uint32_t{5});
    Put(scene.actor+0xad0,base+0xc000); Put(base+0xc018,std::uint32_t{1}); Put(base+0xc020,std::uint32_t{1});
    Put(base+0x45cc,80.0f); Put(base+0x45d0,100.0f);
    unsigned role=1;
    for(auto rva:{0x1373238U,0x13732a8U,0x1373098U,0x1373080U,0x13730b0U,0x1373148U}) { Put(base+rva+4,role++); }
}
c::wire::Command Command(bool npc=false) {
    c::wire::Command result{}; result.authority=npc?c::wire::Authority::npc:c::wire::Authority::manual_player;
    result.local_key[0]=100; result.local_key[1]=53; result.target_key[0]=200; result.target_key[1]=npc?37:53;
    result.actor_hint=static_cast<std::uint32_t>(scene.actor); result.target_hint=static_cast<std::uint32_t>(base+0x4000);
    result.engagement.back()=1; result.request.back()=1;
    c::wire::Text local{reinterpret_cast<const std::uint16_t*>(L"Local"),5},shard{reinterpret_cast<const std::uint16_t*>(L"Shard"),5};
    assert(c::wire::IdentityDigest(local.units,local.count,result.local_name));
    assert(c::wire::IdentityDigest(shard.units,shard.count,result.server));
    c::wire::IdentityJson owner,entry; assert(owner.Literal("[\"Shard\", \"Local\"]") && owner.Finish(result.owner));
    if(!npc) {
        assert(c::wire::IdentityDigest(reinterpret_cast<const std::uint16_t*>(L"Target"),6,result.target_name));
        assert(entry.Literal("[\"player\", \"Shard\", \"000000c8:00000035\"]") && entry.Finish(result.entry));
    } else { Put(base+0x401c,std::uint32_t{37}); }
    return result;
}
}
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& value) noexcept { return live && value.epoch==1; }
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
}
namespace wonderbane::extension::combat::submission {
bool Ready() noexcept { return true; }
Boundary::Boundary() noexcept {} void Boundary::Restore() noexcept { ++restores; }
Scope::Scope(const Context& value) noexcept { melee_context=value; }
Scope::~Scope() {}
Receipt Scope::Finish() noexcept { if(melee_context.receipt) { *melee_context.receipt=melee_receipt; } return melee_receipt; }
}
namespace wonderbane::extension::combat::power {
std::uint64_t InitiationEpoch() noexcept { return epoch; }
bool NativeUseInFlight() noexcept { return native_in_flight; }
bool Ready() noexcept { return true; }
Boundary::Boundary() noexcept {} void Boundary::Restore() noexcept { ++restores; }
Scope::Scope(const Context& value) noexcept:context_(value) { power_context=value; }
Scope::~Scope() {}
Receipt Scope::Finish() noexcept { if(power_context.receipt) { *power_context.receipt=power_receipt; } return power_receipt; }
bool ReadSelfInitiation(std::uintptr_t,std::uintptr_t,std::uint32_t,InitiationDefinition& out) {
    if(!definition_available) { return false; }
    out={base+0x10000+definition_generation*4,learned_rank,initiation_seconds};
    if(mutate_after_definition) { mutate_on_current=true; } return true;
}
bool Invoke(Scope& scope) {
    ++casts; assert(scope.Binding().power_id==428918601);
    if(power_context.receipt) { *power_context.receipt=power_receipt; }
    if(!power_receipt.native_entered) {
        if(availability_change==1) { admitted=false; }
        if(availability_change==2) { mutate_on_current=true; }
        return false;
    }
    Put(scene.actor+0x9bc,std::uint32_t{12}); Put(base+0xc020,std::uint32_t{4});
    Put(base+0xc010,std::uint32_t{6}); Protocol({scope.Binding().power_id});
    assert(power_context.current(power_context.owner)); // Native entry may legitimately become busy.
    return true;
}
}
namespace wonderbane::extension::combat::melee {
void Release(void*& value) { if(value) { assert(references[value]); --references[value]; value=nullptr; } }
bool Invoke(std::uintptr_t image,void* actor,void* target,submission::Scope&,void*& request,void*&,
    Admission current,void* context) {
    ++attacks; assert(image==base && actor==reinterpret_cast<void*>(scene.actor) && target==reinterpret_cast<void*>(base+0x4000));
    if(throw_attack || seh_attack) {
        request=reinterpret_cast<void*>(base+0xe000); ++references[request];
        *melee_context.receipt=melee_receipt;
        if(seh_attack) { RaiseException(0xe0005555,0,0,nullptr); }
        throw std::runtime_error("owned request fault");
    }
    if(mutate_before_entry) { ++epoch; assert(!current(context)); melee_receipt={}; Put(base+0xc018,std::uint32_t{2}); return false; }
    if(melee_context.receipt) { *melee_context.receipt=melee_receipt; }
    if(mutate_after_entry) { ++epoch; }
    Put(base+0xc020,std::uint32_t{2}); Put(scene.actor+0xaf8,base+0x4000);
    assert(current(context)); return true;
}
}

namespace a=wonderbane::extension::actor;
using AO=a::wire::Outcome;using AE=a::wire::Entry;using AL=a::wire::LocalSettlement;
namespace {
unsigned items{},publications{};
bool publication_current=true,item_fault=false,publication_fault=false,release_fault=false;
std::function<void()> publication_callback;
void PublicationCallback(){if(publication_callback){auto callback=std::exchange(publication_callback,{});callback();}}
bool SceneCurrent(void*)noexcept{return live;}
a::fence::ActorBinding Parent(){
    const auto legacy=Command();a::fence::ActorBinding p{};
    p.client_pid=p.producer_pid=GetCurrentProcessId();
    p.client_creation=p.producer_creation=a::fence::Creation(GetCurrentProcess());
    p.producer_generation=p.movement_generation=p.scene=1;p.owner_id.back()=1;
    p.actor_key[0]=100;p.actor_key[1]=53;p.actor_hint=static_cast<std::uint32_t>(scene.actor);
    p.local_name=legacy.local_name;p.server=legacy.server;p.owner=legacy.owner;
    m::wire::Token token{};strcpy_s(token.worker,"worker");strcpy_s(token.operation,"operation");
    assert(a::fence::Hash(&token,sizeof(token),p.operation));assert(a::fence::Valid(p));return p;
}
a::fence::ContextBinding Child(const a::fence::ActorBinding& parent){
    a::fence::ContextBinding child{};assert(a::fence::HashBinding(parent,child.parent_digest));
    child.context_id.back()=1;child.authority=2;child.target_hint=static_cast<std::uint32_t>(base+0x4000);
    child.target_key[0]=200;child.target_key[1]=37;Put(base+0x401c,std::uint32_t{37});assert(a::fence::Parent(child,parent));return child;
}
a::wire::Command Typed(const a::fence::ActorBinding& parent,const a::fence::ContextBinding* child,a::wire::Action action){
    a::wire::Command command{};command.host={parent.producer_pid,1,parent.producer_creation};
    command.window=reinterpret_cast<std::uintptr_t>(window);command.grant.generation=command.grant.scene=1;command.grant.owner=1;
    strcpy_s(command.grant.token.worker,"worker");strcpy_s(command.grant.token.operation,"operation");
    command.request.back()=1;command.parent_id=parent.owner_id;assert(a::fence::HashBinding(parent,command.parent_digest));
    if(child){command.context_id=child->context_id;assert(a::fence::HashBinding(*child,command.context_digest));}
    command.action=action;
    if(action==a::wire::Action::self_power||action==a::wire::Action::cast){command.power_id=428918601;}
    command.recipient=(action==a::wire::Action::self_power||action==a::wire::Action::use_item)?a::wire::Recipient::actor:a::wire::Recipient::target;
    if(!child){command.selector_index=0;command.manifest_digest.fill(2);command.publication_revision=1;command.snapshot_id.back()=1;}
    if(action==a::wire::Action::use_item){command.item_key[0]=55;command.item_key[1]=30;command.template_key[0]=980066;
        command.item_hint=static_cast<std::uint32_t>(base+0xe000);command.template_hint=static_cast<std::uint32_t>(base+0xe800);}
    assert(a::wire::Valid(a::wire::Verb::submit,command));assert(a::wire::Bindings(command,parent,child));return command;
}
a::NativeActor::Gates Gates(){return {Current,Current,nullptr};}
}
namespace wonderbane::extension::combat::item {
Receipt Invoke(const Context& c,State& state,Receipt& receipt)noexcept{
    ++items;assert(!state.attempted&&c.current(c.owner)&&c.item_address==base+0xe000&&c.template_address==base+0xe800);
    assert((c.item_key==Key{55,30}&&c.template_key==Key{980066,0}&&c.template_type==8&&c.template_flags==10));
    state.attempted=true;receipt={Result::queued,true,true,true,false};
    if(item_fault){state.quarantined=true;receipt.ownership_quarantined=true;receipt.result=Result::uncertain;}
    return receipt;
}
}
namespace wonderbane::extension::actor_buffs {
Unknown Capture(const actor_effects::Context& c,const Request& request,State&,Publication& out)noexcept{
    PublicationCallback();if(publication_fault){RaiseException(0xe0007777,0,0,nullptr);}
    ++publications;out={};if(!c.current(c.owner)){return Unknown::identity;}
    out.unknown=Unknown::none;out.actor_key=c.actor_key;out.scene=c.scene;out.effect_epoch=1;out.count=request.count;
    for(std::uint32_t i=0;i<request.count;++i){out.actions[i].intent=request.actions[i];}
    return Unknown::none;
}
bool Revalidate(const actor_effects::Context& c,State&,const Publication& out)noexcept{PublicationCallback();return publication_current&&out.Complete()&&c.current(c.owner);}
bool Release(State&)noexcept{PublicationCallback();return true;}
bool ItemOperand(const actor_effects::Context& c,State& state,const Publication& out,std::uint32_t index,combat::inventory::Facts& facts)noexcept{
    if(index||!Revalidate(c,state,out)){return false;}
    facts={{55,30},{980066,0},base+0xe000,base+0xe800,3,8,10};return true;
}
}
namespace wonderbane::extension::actor {
struct NativeActorTestAccess {
    static void** __fastcall Lookup(void* world,void*,void** output,const std::uint32_t* key){
        ++lookups;assert(world==reinterpret_cast<void*>(scene.world)&&!*output&&(key[0]==100||key[0]==200));
        if(lookup_mode==1){return output;}
        *output=reinterpret_cast<void*>(base+(key[0]==100?0x2000:0x4000));++references[*output];
        if(lookup_mode==2){return nullptr;}
        if(lookup_mode==3){RaiseException(0xe0006666,0,0,nullptr);}
        if(lookup_mode==4){throw std::runtime_error("lookup fault");}
        return output;
    }
    static void __fastcall Drop(void** value,void*,void*){if(release_fault){throw std::runtime_error("release fault");}melee::Release(*value);}
    static bool __cdecl Dispatch(const void* action,void*){
        assert(*static_cast<const std::uint32_t*>(action)==0x616);++stops;
        if(!reject_cancel){Put(base+0xc018,std::uint32_t{1});Put(base+0xc010,std::uint32_t{5});
            Put(scene.actor+0xaf8,std::uintptr_t{0});Protocol({});}
        return true;
    }
    static bool Bind(NativeActor& value){
        value.image_=base;value.window_=window;value.thread_=GetCurrentThreadId();value.scene_=scene;
        value.scene_current_=SceneCurrent;value.calls_.lookup=reinterpret_cast<decltype(value.calls_.lookup)>(&Lookup);
        value.calls_.release=reinterpret_cast<decltype(value.calls_.release)>(&Drop);value.calls_.attack=melee::Invoke;
        value.calls_.power=combat::power::Invoke;value.calls_.self_initiation=combat::power::ReadSelfInitiation;
        value.calls_.item=combat::item::Invoke;value.calls_.dispatch=Dispatch;
        return value.BindCxx();
    }
    static void Dispose(NativeActor& value){
        melee::Release(value.actor_);melee::Release(value.target_);melee::Release(value.request_);melee::Release(value.transfer_);
    }
};
}
namespace {
void ActorReset(){Reset();current_callback={};items=publications=0;publication_current=true;item_fault=publication_fault=release_fault=false;publication_callback={};}
void Publish(a::NativeActor& actor,bool item){
    wonderbane::extension::actor_buffs::Request request{};request.count=1;
    request.actions[0].coverage_power_id=428918601;
    if(item){request.actions[0].item_template={980066,0};}else{request.actions[0].power_id=428918601;}
    wonderbane::extension::actor_buffs::Publication published;
    assert(actor.Publish(request,published)==wonderbane::extension::actor_buffs::Unknown::none&&published.Complete());
}
void CloseScene(a::NativeActor& actor){live=false;assert(actor.ReleaseScene());}
}
void AdmissionCases(){
    for(bool owned:{false,true}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();
        std::uint32_t blocks{};Put(scene.actor+0xaf8,base+0x4000);
        assert(actor.ReadAdmission(blocks)&&(blocks&a::admission::foreign_target)); // No parent grants invented ownership.
        Put(scene.actor+0xaf8,std::uintptr_t{});assert(actor.ValidateParent(parent,Gates()));
        if(owned){const auto child=Child(parent);assert(actor.Attach(child,Gates()).outcome==AO::bound);}
        Put(scene.actor+0xaf8,base+0x4000);Publish(actor,false);
        if(owned){current_callback=[&]{
            assert(actor.Submit(Typed(parent,nullptr,a::wire::Action::self_power)).outcome==AO::invalid);
            std::uint32_t nested{};assert(!actor.ReadAdmission(nested)&&!casts);
        };assert(actor.ReadAdmission(blocks)&&!blocks&&!casts);}
        assert(actor.Publication().admission_blocks==(owned?0U:a::admission::foreign_target));
        auto command=Typed(parent,nullptr,a::wire::Action::self_power);auto result=actor.Submit(command);
        if(!owned){assert(result.outcome==AO::deferred&&result.reason==a::wire::Reason::target_occupied
            &&result.entry==AE::never_entered&&result.local_settlement==AL::settled&&!casts&&!stops);
            Put(scene.actor+0xaf8,std::uintptr_t{});Publish(actor,false);assert(!actor.Publication().admission_blocks);
            result=actor.Submit(command);}
        assert(result.outcome==AO::queued&&casts==1&&!stops);
        assert(actor.ReadAdmission(blocks)&&(blocks&a::admission::local_action));
        Protocol({});Put(base+0xc010,std::uint32_t{5});assert(actor.Poll().local_settlement==AL::settled);
        assert(actor.ReadAdmission(blocks)&&!blocks); // Remote application is not a local block.
        CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();
        assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);assert(actor.Attach(child,Gates()).outcome==AO::bound);
        Put(scene.actor+0xaf8,base+0x4000);current_callback=[] {RaiseException(0xe0008888,0,0,nullptr);};
        std::uint32_t blocks{};assert(!actor.ReadAdmission(blocks)&&!actor.Available()&&!casts);
        assert(!actor.ReadAdmission(blocks));a::NativeActorTestAccess::Dispose(actor);
    }
    ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();
    assert(actor.ValidateParent(parent,Gates()));Publish(actor,false);native_in_flight=true;
    auto result=actor.Submit(Typed(parent,nullptr,a::wire::Action::self_power));
    assert(result.reason==a::wire::Reason::native_use&&result.entry==AE::never_entered&&!casts);
    native_in_flight=false;Publish(actor,false);Put(scene.actor+0xad0,std::uintptr_t{});
    std::uint32_t blocks{};assert(!actor.ReadAdmission(blocks));CloseScene(actor);
}
int main(){
    base=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x1800000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));assert(base);
    window=CreateWindowExW(0,L"STATIC",L"actor-native",0,0,0,1,1,HWND_MESSAGE,nullptr,GetModuleHandleW(nullptr),nullptr);assert(window);
    AdmissionCases();
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();
        assert(actor.MatchesIdentity(parent.local_name,parent.server));auto wrong=parent.server;wrong[0]^=1;
        assert(!actor.MatchesIdentity(parent.local_name,wrong));
        assert(actor.ValidateParent(parent,Gates())&&!stops);Publish(actor,true);
        const auto item=Typed(parent,nullptr,a::wire::Action::use_item);const auto result=actor.Submit(item);
        assert(result.outcome==AO::queued&&result.entry==AE::entered&&result.local_settlement==AL::settled&&items==1&&!stops);
        assert(actor.StopOwner(parent,Current,nullptr).closure==a::wire::Closure::local_released&&!stops);
        admitted=false;assert(actor.RevalidatePublication(actor.Publication())&&actor.Available()); // Scene publication is Grant-independent.
        admitted=true;auto newer=parent;newer.owner_id.back()=2;assert(actor.ValidateParent(newer,Gates()));
        Publish(actor,false);auto power=Typed(newer,nullptr,a::wire::Action::self_power);
        const auto cast=actor.Submit(power);assert(cast.outcome==AO::queued&&cast.local_settlement==AL::pending&&casts==1&&!stops);
        assert(power_context.authority==p::Authority::actor&&!power_context.target&&power_context.target_key==p::Key{});
        assert(actor.Submit(power).outcome==AO::deferred&&casts==1);assert(actor.Poll().local_settlement==AL::pending);
        Protocol({});Put(base+0xc010,std::uint32_t{5});Put(base+0xc020,std::uint32_t{2});++epoch;
        assert(actor.Poll().local_settlement==AL::settled); // No animation/action2 wait.
        assert(actor.StopOwner(newer,Current,nullptr).closure==a::wire::Closure::local_released&&!stops);CloseScene(actor);
    }
    for(unsigned changed=0;changed<3;++changed){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,true);
        auto item=Typed(parent,nullptr,a::wire::Action::use_item);
        if(changed==0){item.item_hint+=4;}if(changed==1){item.template_hint+=4;}if(changed==2){publication_current=false;}
        assert(actor.Submit(item).entry==AE::never_entered&&!items&&!stops);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));
        const auto child=Child(parent);assert(actor.Attach(child,Gates()).outcome==AO::bound&&!stops);
        auto attack=Typed(parent,&child,a::wire::Action::attack);assert(actor.Submit(attack).outcome==AO::queued&&attacks==1);
        Put(base+0xc018,std::uint32_t{2});reject_cancel=true;
        assert(actor.StopContext(child,Current,nullptr).outcome==AO::pending&&stops==1&&actor.Available());
        reject_cancel=false;assert(actor.StopContext(child,Current,nullptr).closure==a::wire::Closure::native_stopped&&stops==2);
        assert(actor.ValidateParent(parent,Gates()));auto child2=child;child2.context_id.back()=2;
        assert(actor.Attach(child2,Gates()).outcome==AO::bound);assert(actor.StopContext(child2,Current,nullptr).closure==a::wire::Closure::local_released);
        assert(actor.StopOwner(parent,Current,nullptr).closure==a::wire::Closure::local_released);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        assert(actor.Attach(child,Gates()).outcome==AO::bound);auto skill=Typed(parent,&child,a::wire::Action::self_power);
        assert(actor.Submit(skill).local_settlement==AL::settled);auto attack=Typed(parent,&child,a::wire::Action::attack);attack.request.back()=2;
        assert(actor.Submit(attack).outcome==AO::queued&&attacks==1);attack.request.back()=3;
        assert(actor.Submit(attack).outcome==AO::deferred&&attacks==1);CloseScene(actor);
    }
    for(bool uncertain:{false,true}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,false);
        if(uncertain){power_receipt={p::Result::uncertain,true,false,false,false};}
        power_receipt.observation.use_called=true;power_receipt.observation.use_returned=!uncertain;
        auto command=Typed(parent,nullptr,a::wire::Action::self_power);const auto submitted=actor.Submit(command);
        assert(submitted.local_settlement==AL::pending&&submitted.power_diagnostic.observation.use_called
            &&submitted.power_diagnostic.observation.use_returned==!uncertain
            &&submitted.power_diagnostic.append_observed==!uncertain);
        Protocol({});Put(base+0xc010,std::uint32_t{5});
        if(uncertain){assert(actor.Poll().local_settlement==AL::pending);}else{admitted=false;assert(actor.Poll().local_settlement==AL::pending);admitted=true;}
        Put(base+0xc018,std::uint32_t{2});assert(actor.StopOwner(parent,Current,nullptr).closure==a::wire::Closure::native_stopped);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,false);
        Protocol({123});auto command=Typed(parent,nullptr,a::wire::Action::self_power);
        assert(actor.Submit(command).outcome==AO::deferred&&!casts&&!stops);CloseScene(actor);
    }
    for(const auto availability:{p::Availability::reuse_blocked,p::Availability::global_recovery,p::Availability::unknown}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,false);
        power_receipt={};power_receipt.availability=availability;power_receipt.availability_epoch=epoch;
        auto command=Typed(parent,nullptr,a::wire::Action::self_power);const auto result=actor.Submit(command);
        assert(result.entry==AE::never_entered&&result.local_settlement==AL::settled&&!result.history&&!stops);
        assert(result.outcome==(availability==p::Availability::reuse_blocked?AO::power_reuse_blocked:availability==p::Availability::global_recovery?AO::deferred:AO::unavailable));CloseScene(actor);
    }
    for(unsigned change:{1U,2U}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,false);
        power_receipt={};power_receipt.availability=p::Availability::reuse_blocked;power_receipt.availability_epoch=epoch;
        availability_change=change;auto command=Typed(parent,nullptr,a::wire::Action::self_power);const auto result=actor.Submit(command);
        assert(result.entry==AE::never_entered&&result.outcome!=AO::power_reuse_blocked&&!result.history&&!stops);CloseScene(actor);
    }
    for(const bool with_child:{false,true}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));
        const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        if(with_child){assert(actor.Attach(child,Gates()).outcome==AO::bound);}else{Publish(actor,false);}
        power_receipt={};power_receipt.availability=p::Availability::stance_ineligible;power_receipt.availability_epoch=epoch;
        auto command=Typed(parent,with_child?&child:nullptr,a::wire::Action::self_power);
        const auto result=actor.Submit(command);
        assert(result.outcome==AO::deferred&&result.reason==a::wire::Reason::observation
            &&result.entry==AE::never_entered&&result.local_settlement==AL::settled&&!result.history&&!stops);
        a::wire::Command pending{};assert(!actor.PendingCommand(pending));
        // A positive no-entry refusal cannot leave a synthetic local obligation.
        power_receipt={p::Result::queued,true,true,true,true,epoch};command.request.back()=2;
        assert(actor.Submit(command).outcome==AO::queued);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        assert(actor.Attach(child,Gates()).outcome==AO::bound);Put(base+0x4018,std::uint32_t{201});
        assert(actor.Submit(Typed(parent,&child,a::wire::Action::attack)).entry==AE::never_entered&&!attacks);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,true);
        item_fault=true;const auto result=actor.Submit(Typed(parent,nullptr,a::wire::Action::use_item));
        assert(result.local_settlement==AL::pending&&result.entry==AE::entered&&(result.history&a::wire::outbound_queued)&&!actor.Available());
        assert(actor.StopOwner(parent,Current,nullptr).closure==a::wire::Closure::none);live=false;assert(!actor.ReleaseScene());a::NativeActorTestAccess::Dispose(actor);
    }
    for(unsigned mode:{1U,2U,4U}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        lookup_mode=mode;const auto result=actor.Attach(child,Gates());assert(result.outcome!=AO::bound&&!attacks&&!casts);
        if(mode==1){assert(result.closure==a::wire::Closure::local_released&&result.entry==AE::never_entered&&result.local_settlement==AL::settled);CloseScene(actor);}else{assert(result.closure==a::wire::Closure::none&&result.local_settlement==AL::pending);assert(!actor.Available());a::NativeActorTestAccess::Dispose(actor);}
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        assert(actor.Attach(child,Gates()).outcome==AO::bound);mutate_before_entry=true;
        const auto result=actor.Submit(Typed(parent,&child,a::wire::Action::attack));
        assert(result.entry==AE::unknown&&result.outcome==AO::uncertain&&result.local_settlement==AL::pending&&!(result.history&a::wire::outbound_queued));
        assert(actor.StopContext(child,Current,nullptr).closure==a::wire::Closure::native_stopped);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));Publish(actor,true);
        const auto command=Typed(parent,nullptr,a::wire::Action::use_item);
        auto reenter=[&]{
            assert(actor.Submit(command).entry==AE::never_entered&&!items);
            assert(actor.StopOwner(parent,Current,nullptr).closure==a::wire::Closure::none);
            wonderbane::extension::actor_buffs::Request request{};wonderbane::extension::actor_buffs::Publication out;
            assert(actor.Publish(request,out)!=wonderbane::extension::actor_buffs::Unknown::none);
        };
        publication_callback=reenter;Publish(actor,true);assert(!publication_callback&&actor.Publication().Complete());
        publication_callback=reenter;assert(actor.RevalidatePublication(actor.Publication())&&!publication_callback&&!items);CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));publication_fault=true;
        wonderbane::extension::actor_buffs::Request request{};wonderbane::extension::actor_buffs::Publication out;
        assert(actor.Publish(request,out)==wonderbane::extension::actor_buffs::Unknown::read_fault&&!actor.Available()&&!out.Complete());
        a::NativeActorTestAccess::Dispose(actor);
    }
    for(bool fail_release:{false,true}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        Put(base+0x4018,std::uint32_t{201});release_fault=fail_release;const auto result=actor.Attach(child,Gates());
        assert(result.outcome!=AO::bound&&!attacks&&!casts);
        if(fail_release){assert(result.closure==a::wire::Closure::none&&result.entry==AE::unknown&&result.local_settlement==AL::pending&&!actor.Available());a::NativeActorTestAccess::Dispose(actor);}
        else{assert(result.closure==a::wire::Closure::local_released&&result.entry==AE::never_entered&&result.local_settlement==AL::settled);CloseScene(actor);}
    }
    for(bool seh:{false,true}){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);
        assert(actor.Attach(child,Gates()).outcome==AO::bound);auto command=Typed(parent,&child,a::wire::Action::attack);throw_attack=!seh;seh_attack=seh;
        const auto before=restores;const auto result=actor.Submit(command);
        assert(result.outcome==AO::uncertain&&result.entry==AE::entered&&(result.history&a::wire::outbound_queued)&&result.local_settlement==AL::pending&&restores==before+2);
        assert(!actor.Available());live=false;assert(!actor.ReleaseScene());a::NativeActorTestAccess::Dispose(actor);
    }
    for(unsigned changed=0;changed<6;++changed){
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();
        assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);assert(actor.Attach(child,Gates()).outcome==AO::bound);
        assert(actor.Submit(Typed(parent,&child,a::wire::Action::attack)).local_settlement==AL::settled);
        assert(actor.ContinueContext());const auto attack_count=attacks,stop_count=stops;
        if(changed==0){Put(base+0x4018,std::uint32_t{201});}
        if(changed==1){
            Put(base+0x8100,base+0x8200);Put(base+0x8104,base+0x8200);
            Put(base+0x8200,base+0x8100);Put(base+0x8204,base+0x8100);Put(base+0x8208,base+0x8300);
            Put(base+0x8310,std::array<std::uint32_t,2>{200,37});
        }
        if(changed==2){Put(scene.actor+0xaf8,base+0x5000);}
        if(changed==3){Put(base+0x45cc,0.0f);}
        if(changed==4){Put(base+0x4034,base+0x8500);Put(base+0x8500,std::uint32_t{1});Put(base+0x8504,base+0x8600);
            Put(base+0x8604,base+0x8700);Put(base+0x8700,std::uint8_t{1});}
        if(changed==5){Put(scene.actor+0xad0,std::uintptr_t{0});}
        assert(!actor.ContinueContext()&&actor.Available()&&attacks==attack_count&&stops==stop_count);
        CloseScene(actor);
    }
    {
        ActorReset();a::NativeActor actor;assert(a::NativeActorTestAccess::Bind(actor));const auto parent=Parent();
        assert(actor.ValidateParent(parent,Gates()));const auto child=Child(parent);assert(actor.Attach(child,Gates()).outcome==AO::bound);
        initiation_seconds=1;assert(actor.Submit(Typed(parent,&child,a::wire::Action::cast)).local_settlement==AL::pending);
        assert(actor.ContinueContext()&&!stops&&casts==1); // Busy cast with null AF8 remains owned.
        current_callback=[&]{assert(!actor.ContinueContext());assert(actor.StopContext(child,Current,nullptr).closure==a::wire::Closure::none);};
        assert(actor.ContinueContext()&&!current_callback&&!stops);
        current_callback=[] {RaiseException(0xe0008888,0,0,nullptr);};
        assert(!actor.ContinueContext()&&!actor.Available()&&!stops);
        assert(!actor.ContinueContext());a::NativeActorTestAccess::Dispose(actor);
    }
    ActorReset();DestroyWindow(window);VirtualFree(reinterpret_cast<void*>(base),0,MEM_RELEASE);return 0;
}
