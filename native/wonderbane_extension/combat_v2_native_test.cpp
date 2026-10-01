#include "combat_v2_native.h"
#undef NDEBUG
#include <cassert>
#include <map>
#include <stdexcept>
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
std::map<void*,unsigned> references;
s::Context melee_context{}; p::Context power_context{};
s::Receipt melee_receipt{s::Result::queued,true,true,true};
p::Receipt power_receipt{p::Result::queued,true,true,true,true};
template<class T> void Put(std::uintptr_t at,T value) { std::memcpy(reinterpret_cast<void*>(at),&value,sizeof(value)); }
bool Current(void*) noexcept { if(mutate_on_current) { ++epoch; mutate_on_current=false; } return admitted; }
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
    if(mutate_before_entry) { ++epoch; assert(!current(context)); return false; }
    if(melee_context.receipt) { *melee_context.receipt=melee_receipt; }
    if(mutate_after_entry) { ++epoch; }
    Put(base+0xc020,std::uint32_t{2}); Put(scene.actor+0xaf8,base+0x4000);
    assert(current(context)); return true;
}
}
namespace wonderbane::extension::combat::v2 {
struct NativeTargetTestAccess {
    static void** __fastcall Lookup(void* world,void*,void** output,const std::uint32_t* key) {
        ++lookups; assert(world==reinterpret_cast<void*>(scene.world) && key[0]==200 && !*output);
        if(lookup_mode==1) { return output; }
        *output=reinterpret_cast<void*>(base+0x4000); ++references[*output];
        if(lookup_mode==2) { return nullptr; }
        if(lookup_mode==3) { RaiseException(0xe0006666,0,0,nullptr); }
        if(lookup_mode==4) { throw std::runtime_error("lookup output assigned"); }
        if(lookup_mode==5) { Put(base+0x4018,std::uint32_t{201}); }
        if(lookup_mode==6) { Put(base+0x1389028,scene.world+4); }
        if(lookup_mode==7) { admitted=false; }
        return output;
    }
    static void __fastcall Retain(void*,void*,void** value) { ++references[*value]; }
    static void __fastcall Release(void** value,void*,void*) { melee::Release(*value); }
    static bool __cdecl Dispatch(const void* action,void*) {
        assert(*static_cast<const std::uint32_t*>(action)==0x616); ++stops;
        if(!reject_cancel) { Put(base+0xc018,std::uint32_t{1}); Put(base+0xc020,std::uint32_t{1}); Put(scene.actor+0x9bc,std::uint32_t{0}); Put(scene.actor+0xaf8,std::uintptr_t{0}); }
        return true;
    }
    static void Bind(NativeTarget& value) {
        value.base_=base; value.window_=window; value.thread_=GetCurrentThreadId();
        value.calls_.lookup=reinterpret_cast<decltype(value.calls_.lookup)>(&Lookup);
        value.calls_.retain=reinterpret_cast<decltype(value.calls_.retain)>(&Retain);
        value.calls_.release=reinterpret_cast<decltype(value.calls_.release)>(&Release);
        value.calls_.self_initiation=&power::ReadSelfInitiation;
        value.calls_.attack=&melee::Invoke; value.calls_.cast=&power::Invoke; value.calls_.dispatch=&Dispatch;
    }
    static void Dispose(NativeTarget& value) {
        melee::Release(value.request_); melee::Release(value.transfer_); melee::Release(value.actor_); melee::Release(value.target_);
    }
};
}
int main() {
    base=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x1800000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)); assert(base);
    window=CreateWindowExW(0,L"STATIC",L"v2native",0,0,0,1,1,HWND_MESSAGE,nullptr,GetModuleHandleW(nullptr),nullptr); assert(window);
    for(bool npc:{false,true}) {
        Reset(); auto command=Command(npc); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound && !attacks && !casts && !stops);
        command.action=c::wire::Action::attack;
        assert(target.Execute(command).outcome==O::client_outbound_queued && attacks==1 && lookups==1);
        // A persistent action2 and any animation event index are not pending initiation.
        Put(scene.actor+0x9bc,std::uint32_t{99}); command.request.back()=2;
        assert(target.Execute(command).outcome==O::client_outbound_queued && attacks==2);
        Put(base+0xc020,std::uint32_t{1});
        command.request.back()=3; command.action=c::wire::Action::cast; command.power_id=428918601;
        assert(target.Execute(command).outcome==O::client_outbound_queued && casts==1 && lookups==1);
        assert(target.Prepared() && !stops && target.Clear());
    }
    {
        Reset(); auto command=Command(true); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        command.action=c::wire::Action::self_power; command.power_id=428918601;
        const auto receipt=target.Execute(command);
        assert(receipt.outcome==O::client_outbound_queued && receipt.history&c::wire::outbound_queued);
        assert(power_context.target_mode==p::TargetMode::self && power_context.Recipient()==scene.actor);
        assert(power_context.target==base+0x4000 && power_context.target_key[0]==200);
        assert(power_context.RecipientKey()[0]==100 && command.target_key[0]==200);
        assert(references[reinterpret_cast<void*>(scene.actor)]==1 && references[reinterpret_cast<void*>(base+0x4000)]==1);
        command.request.back()=2; command.action=c::wire::Action::attack; command.power_id=0;
        // Exact owned instant self-power may hand off without waiting for animation/state6.
        assert(target.Execute(command).outcome==O::client_outbound_queued && attacks==1 && casts==1);
        command.request.back()=3;
        assert(target.Execute(command).outcome==O::deferred && attacks==1); // Allowance consumed once.
        assert(target.Clear());
    }
    for(const auto reason:{p::Availability::reuse_blocked,p::Availability::global_recovery,p::Availability::unknown}) {
        Reset();auto command=Command(true);c::NativeTarget target;c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        command.action=c::wire::Action::self_power;command.power_id=428918601;
        power_receipt={};power_receipt.availability=reason;power_receipt.availability_epoch=epoch;
        const auto reply=target.Execute(command);
        assert(reply.entry==c::wire::Entry::never_entered&&!reply.history&&!attacks&&!stops);
        assert(reply.outcome==(reason==p::Availability::reuse_blocked?O::power_reuse_blocked:
            reason==p::Availability::global_recovery?O::deferred:O::unavailable));
        // No-entry refusal preserves engagement for an exact new basic attack.
        command.request.back()=2;command.action=c::wire::Action::attack;command.power_id=0;
        assert(target.Execute(command).outcome==O::client_outbound_queued&&attacks==1&&lookups==1);
        assert(target.Clear());
    }
    for(unsigned change=1;change<=2;++change) {
        Reset();auto command=Command(true);c::NativeTarget target;c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        command.action=c::wire::Action::self_power;command.power_id=428918601;
        power_receipt={};power_receipt.availability=p::Availability::reuse_blocked;
        power_receipt.availability_epoch=epoch;availability_change=change;
        const auto reply=target.Execute(command);
        assert(reply.outcome==(change==1?O::stale:O::deferred)
            &&reply.entry==c::wire::Entry::never_entered&&!reply.history);
        assert(!attacks&&!stops);assert(target.Clear());
    }
    for(unsigned scenario=0;scenario<15;++scenario) {
        Reset(); auto command=Command(true); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        if(scenario==0) { initiation_seconds=1; }
        if(scenario==1) { power_receipt={p::Result::uncertain,true,true,true,true}; }
        if(scenario==2) { power_receipt={p::Result::entered,true,false,false,true}; }
        command.action=c::wire::Action::self_power; command.power_id=428918601;
        (void)target.Execute(command);
        if(scenario==3) { ++learned_rank; }
        if(scenario==4) { ++definition_generation; }
        if(scenario==5) { Protocol({428918601,428918601,428918601}); }
        if(scenario==6) { Protocol({428918601,123}); }
        if(scenario==7) { definition_available=false; }
        if(scenario==8) { Protocol({428918601,428918601}); }
        if(scenario==9) { admitted=false; }
        if(scenario==10) { ++epoch; Protocol({428918601}); } // Removed/re-added same ID is foreign history.
        if(scenario==11) { epoch=0; } // Saturated epoch cannot collide.
        if(scenario==13) { mutate_after_entry=true; }
        if(scenario==14) { mutate_after_definition=true; }
        if(scenario==12) { mutate_before_entry=true; melee_receipt={s::Result::denied,false,false,false}; }
        command.request.back()=2; command.action=c::wire::Action::attack; command.power_id=0;
        const auto result=target.Execute(command);
        assert(((scenario==8||scenario==13) ? result.outcome==O::client_outbound_queued && attacks==1
            : result.outcome!=O::client_outbound_queued && (scenario==12?attacks==1:!attacks)));
        assert(target.Clear());
    }
    // Both stationary and moving native initiation must preserve foreign work.
    for(const auto state:{5U,6U}) {
        Reset(); auto command=Command(true); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        Put(base+0xc010,state); Protocol({123});
        command.action=c::wire::Action::attack;
        assert(target.Execute(command).outcome==O::deferred && !attacks);
        Protocol({});
        assert(target.Execute(command).outcome==(state==6?O::deferred:O::client_outbound_queued));
        assert(target.Clear());
    }
    {
        Reset();auto command=Command(true);c::NativeTarget target;c::NativeTargetTestAccess::Bind(target);
        native_in_flight=true;
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::deferred);
        native_in_flight=false;
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        native_in_flight=true;command.action=c::wire::Action::attack;
        assert(target.Execute(command).outcome==O::deferred);
        c::NativeTarget::Observation state{};assert(!target.Cancel(scene,Current,nullptr,state));
        assert(!attacks&&!casts&&!stops);native_in_flight=false;assert(target.Clear());
    }
    for(unsigned scenario=0;scenario<4;++scenario) {
        Reset(); auto command=Command(true); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        Put(base+0xc010,std::uint32_t{6}); Put(base+0xc020,std::uint32_t{4}); Put(scene.actor+0x9bc,std::uint32_t{1});
        Put(scene.actor+0xaf8,scenario==0?base+0x4000:scenario==1?base+0x6000:std::uintptr_t{0});
        if(scenario==3) { Put(base+0xc010,std::uint32_t{5}); Put(base+0xc020,std::uint32_t{1}); Put(scene.actor+0x9bc,std::uint32_t{0}); Put(base+0xc018,std::uint32_t{2}); }
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==((scenario==0||scenario==3)?O::bound:O::deferred));
        assert(!attacks && !casts && !stops && target.Clear());
    }
    for(bool seh:{false,true}) {
        Reset(); auto command=Command(); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        command.action=c::wire::Action::attack; throw_attack=!seh; seh_attack=seh; const auto before=restores;
        const auto result=target.Execute(command);
        assert(result.outcome==O::uncertain && result.entry==c::wire::Entry::entered && result.history&c::wire::outbound_queued);
        assert(restores==before+2 && !target.Available()); const auto refs=references;
        assert(!target.Clear() && references==refs); c::NativeTargetTestAccess::Dispose(target);
    }
    for(unsigned mode=1;mode<=7;++mode) {
        Reset(); auto command=Command(); lookup_mode=mode;
        c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        const auto result=target.Prepare(scene,command,Current,Current,nullptr);
        assert(result.outcome!=O::bound && !attacks && !casts && !stops);
        if(mode>=2 && mode<=4) {
            const auto refs=references; assert(!target.Available() && !target.Clear() && references==refs);
            c::NativeTargetTestAccess::Dispose(target);
        } else { assert(target.Clear()); }
    }
    for(unsigned bad=0;bad<6;++bad) {
        Reset(); auto command=Command();
        if(bad==0) { Text(base+0x4c48,base+0x4d00,L"Reused"); }
        if(bad==1) { Text(base+0x4c90,base+0x4d80,L"Other"); }
        if(bad==2) { Put(base+0x4d0c,std::uint16_t{1}); }
        if(bad==3) { command.owner.fill(9); }
        if(bad==4) { Put(base+0x8104,std::uintptr_t{1}); }
        if(bad==5) { Put(scene.actor+0x65c,std::uint32_t{1}); }
        c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome!=O::bound);
        assert(!attacks && !casts && !stops && target.Clear());
    }
    {
        Reset(); auto command=Command(); c::NativeTarget target; c::NativeTargetTestAccess::Bind(target);
        assert(target.Prepare(scene,command,Current,Current,nullptr).outcome==O::bound);
        Put(base+0xc018,std::uint32_t{2}); Put(scene.actor+0xaf8,base+0x4000); reject_cancel=true;
        c::NativeTarget::Observation state{};
        assert(!target.Cancel(scene,Current,nullptr,state) && state.target==base+0x4000);
        Put(base+0xc018,std::uint32_t{1}); Put(base+0xc020,std::uint32_t{4}); Put(scene.actor+0xaf8,std::uintptr_t{0});
        Put(base+0xc010,std::uint32_t{6});
        assert(!target.Cancel(scene,Current,nullptr,state)); // No target does not prove initiation settled.
        Put(base+0xc010,std::uint32_t{5}); Protocol({428918601});
        assert(!target.Cancel(scene,Current,nullptr,state));
        Protocol({}); Put(base+0xc020,std::uint32_t{2}); Put(scene.actor+0x9bc,std::uint32_t{23});
        assert(target.Cancel(scene,Current,nullptr,state) && target.Clear());
    }
    Reset(); auto command=Command(true); ++command.target_hint; c::NativeTarget mismatch; c::NativeTargetTestAccess::Bind(mismatch);
    assert(mismatch.Prepare(scene,command,Current,Current,nullptr).outcome==O::stale && mismatch.Clear());
    for(const auto& [object,count]:references) { (void)object; assert(!count); }
    assert(DestroyWindow(window)); assert(VirtualFree(reinterpret_cast<void*>(base),0,MEM_RELEASE));
}
