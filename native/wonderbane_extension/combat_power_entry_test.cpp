#include "combat_power_observer.cpp"
#include "combat_power_entry.cpp"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <vector>
#include <thread>
namespace pw = wonderbane::extension::combat::power;
namespace sb = wonderbane::extension::combat::submission;
namespace {
int failures{};
const char* image_digest="";
std::uintptr_t verified_image{};
unsigned verification_calls{};
int references = 2;
void Check(bool ok, const char* label) { if (!ok) { ++failures; std::fprintf(stderr, "%s\n", label); } }
sb::AppendObserver registered{};
unsigned sends{}, appends{}, followups{}, releases{}, uses{}, lookups{};
bool current = true, queue_current = true, fault_send = false, fault_followup = false;
bool seh_send = false, seh_followup = false, corrupt_key = false;
int learned_rank = 20;
std::uint32_t actor_mode = 1;
unsigned stance_reads{}, stance_toggles{};
bool deny_stance{}, revoke_stance{}, revoke_mode_read{}, fault_stance{}, seh_stance{};
bool epoch_during_mode_read{}, combat_during_availability{};
std::uint32_t* replaced_target_key{};
std::uint32_t __fastcall Mode(void*, void*) {
    ++stance_reads;
    if (revoke_mode_read) { current=false; }
    if (epoch_during_mode_read) { pw::AdvanceEpoch(); }
    return actor_mode;
}
void __fastcall Toggle(void*, void*, bool combat, bool force) {
    ++stance_toggles;
    Check(combat && force, "stance uses ordinary forced combat ABI");
    Check(pw::active && pw::active->Binding().receipt->native_entered,
        "stance side effects are recorded before native entry");
    if (seh_stance) { RaiseException(0xe0420201,0,0,nullptr); }
    if (fault_stance) { throw std::runtime_error("stance"); }
    if (!deny_stance) { actor_mode=2; }
    if (revoke_stance) { current=false; }
    if (replaced_target_key) { ++*replaced_target_key; }
}
unsigned installation_steps{};
bool PartialInstall(pw::Site& site) noexcept { return ++installation_steps==1 && pw::InstallByte(site); }
std::array<std::uint32_t,0xb0/4> message{};
std::array<std::uint32_t,0x300/4> definition{};
void* queue{};
std::uint32_t* current_message=message.data();
bool unrelated{}, reenter_send{}, reenter_followup{}, revoke_during_use{};
std::uint32_t unrelated_power=428918601;
pw::Receipt* outer_receipt{};
void* last_actor{};void* last_target{};
unsigned ordinary_calls{}; bool ordinary_nested=false,ordinary_fault=false,ordinary_throw=false;
bool __cdecl OrdinaryFixture(std::uint32_t id,int rank,void* actor_arg,void* target_arg,const float* position,pw::Key key) {
    ++ordinary_calls;
    Check(pw::NativeUseInFlight(),"ordinary Use is protected before state/vector publication");
    Check(id==123&&rank==40&&actor_arg==reinterpret_cast<void*>(16)&&target_arg==reinterpret_cast<void*>(32)
        &&position==nullptr&&key==pw::Key{7,8},"ordinary Use exact cdecl arguments preserved");
    if(ordinary_nested) {
        ordinary_nested=false;
        Check(pw::OrdinaryUseHook(id,rank,actor_arg,target_arg,position,key),"nested ordinary Use forwards");
        Check(pw::NativeUseInFlight(),"nested return preserves parent in-flight state");
    }
    if(ordinary_fault) { RaiseException(0xe0424243,0,0,nullptr); }
    if(ordinary_throw) { throw 42; }
    SetLastError(4321);return true;
}
bool OrdinaryCall() { return pw::OrdinaryUseHook(123,40,reinterpret_cast<void*>(16),reinterpret_cast<void*>(32),nullptr,pw::Key{7,8}); }
bool OrdinarySeh() {
    __try { (void)OrdinaryCall(); }
    __except(GetExceptionCode()==0xe0424243?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
void Nested();
bool Current(void*) noexcept { return current; }
bool QueueCurrent(void*) noexcept { return queue_current; }
void __fastcall Release(void*, void*, void** empty) { Check(!*empty, "consumed reference starts empty"); ++releases; --references; }
void __fastcall Send(void*, void*, void* value) {
    ++sends;
    if(unrelated){Check(registered.claim(queue,value,0x2c6eb7).decision==sb::AppendDecision::unrelated,"nested message never borrows outer ticket");return;}
    if(reenter_send){reenter_send=false;Nested();}
    if (!pw::active) { ++releases; return; }
    if (seh_send) { RaiseException(0xe0420201, 0, 0, nullptr); }
    if (fault_send) { throw std::runtime_error("send"); }
    const auto claim = registered.claim(queue, value, 0x2c6eb7);
    Check(claim.decision != sb::AppendDecision::unrelated, "exact message claimed");
    if (claim.decision == sb::AppendDecision::allow) { ++appends; registered.complete(claim.owner, sb::AppendResult::queued); }
    else { registered.complete(claim.owner, sb::AppendResult::denied); ++releases; }
}
void __cdecl Followup(void*, void*, void*, int) {
    ++followups;
    if(unrelated){return;}
    if(reenter_followup){reenter_followup=false;Nested();}
    if (seh_followup) { RaiseException(0xe0420201, 0, 0, nullptr); }
    if (fault_followup) { throw std::runtime_error("followup"); }
}
void* __cdecl Definition(std::uint32_t id) { ++lookups; Check(id == 428918601, "semantic native ID"); return definition.data(); }
int __fastcall Rank(void*, void*, std::uint32_t) { return learned_rank; }
void* sender{};
pw::Use native_use{};
bool __cdecl RefusedUse(std::uint32_t,int,void*,void*,const float*,pw::Key) {SetLastError(7654);return false;}
bool __cdecl Use(std::uint32_t id, int rank, void* actor, void* target, const float* position, pw::Key key) {
    ++uses; last_actor=actor;last_target=target;Check((id == 428918601 || unrelated) && rank == std::min(learned_rank,9999), "native learned rank");
    Check(key == pw::Key{} && position[0] == 0 && position[1] == 0 && position[2] == 0, "zero key preserves native target validation");
    current_message[0x80/4]=id;
    current_message[0x84/4] = static_cast<std::uint32_t>(rank);
    if (corrupt_key) { ++current_message[0x90/4]; }
    if (revoke_during_use) { current=false; }
    return true;
}
void Nested() {
    const auto before=*outer_receipt;
    const auto sends_before=sends, effects_before=followups;
    auto nested=message;
    current_message=nested.data();unrelated=true;
    const float position[3]{};
    native_use(unrelated_power,20,last_actor,last_target,position,pw::Key{});
    unrelated=false;current_message=message.data();
    Check(sends==sends_before+1 && followups==effects_before+1,"nested native calls pass through both sites");
    Check(outer_receipt->result==before.result && outer_receipt->native_entered==before.native_entered
        && outer_receipt->send_observed==before.send_observed && outer_receipt->append_observed==before.append_observed
        && outer_receipt->followup_entered==before.followup_entered,"nested same/different power leaves outer receipt unchanged");
}
pw::Availability availability = pw::Availability::ready;
pw::Availability ReadAvailability(std::uintptr_t,std::uintptr_t,std::uint32_t) noexcept {
    if(combat_during_availability){actor_mode=2;}
    return availability;
}
void Run(const pw::Context& c) { pw::Scope scope(c); (void)pw::InvokeBound(scope, {Definition,reinterpret_cast<pw::Rank>(&Rank),native_use,
    {reinterpret_cast<wonderbane::extension::combat::stance::Getter>(&Mode),
     reinterpret_cast<wonderbane::extension::combat::stance::Toggle>(&Toggle)},ReadAvailability}); }
bool Guarded(const pw::Context& c) {
    pw::Boundary boundary;
    __try { __try { Run(c); } __finally { boundary.Restore(); } }
    __except(GetExceptionCode()==0xe0420201 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { return false; }
    return true;
}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char* digest) noexcept { return std::strcmp(digest,image_digest)==0; }
namespace movement { bool VerifyNativeMovementImage(std::uintptr_t& output) noexcept { ++verification_calls; output=verified_image; return output!=0; } }
namespace combat::submission {
bool RegisterAppendObserver(AppendObserverKind kind, const AppendObserver& observer) noexcept { if(kind != AppendObserverKind::power) { return false; } registered = observer; return true; }
}
}
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
#include "combat_power_probe_support.h"
#endif
int main(int argc, char** argv) {
    (void)argc; (void)argv;
    auto* image = static_cast<unsigned char*>(VirtualAlloc(nullptr,0x16ac000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if (!image) { return 2; }
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    const auto put = [base](std::uintptr_t at, std::uintptr_t value) { *reinterpret_cast<std::uintptr_t*>(base+at)=value; };
    std::array<std::uint32_t,0xae0/4> actor{};
    std::array<std::uint32_t,0x700/4> target{};
    std::array<std::uint32_t,8> diagnostic_state{};
    diagnostic_state[4]=5;diagnostic_state[6]=2;diagnostic_state[7]=3;
    actor[0xad0/4]=reinterpret_cast<std::uint32_t>(diagnostic_state.data());
    const pw::Key local{123,53}, victim{456,37};
    actor[0]=static_cast<std::uint32_t>(base+0x114165c); actor[6]=local[0]; actor[7]=local[1];
    target[6]=victim[0]; target[7]=victim[1];
    put(0x16a2d98,reinterpret_cast<std::uintptr_t>(actor.data()));
    put(0x16ab88c,base+0x1600000); put(0x1600000,base+0x116036c);
    put(0x1600044,base+0x1600100); put(0x1600100,base+0x114ce9c);
    put(0x1155fd8+8,reinterpret_cast<std::uintptr_t>(&Release));
    queue=reinterpret_cast<void*>(base+0x1600100); sender=reinterpret_cast<void*>(base+0x16ab888);
    definition[0x138/4]=428918601; definition[0x204/4]=0; definition[0x1a8/4]=1;
    for (const auto& site:pw::sites) { std::memcpy(image+site.rva,site.bytes.data(),5); }
    // Synthetic bodies preserve the reviewed 9bbf0 -> 9c710 EBP chain and
    // genuine return site9bf09. The production bridge must identify THIS entry,
    // not merely a same-shaped message reached through an unrelated invocation.
    const auto imm=[](unsigned char*& at,std::uintptr_t v){std::memcpy(at,&v,4);at+=4;};
    const auto byte=[](unsigned char*& at,std::initializer_list<unsigned char> bytes){for(auto v:bytes){*at++=v;}};
    const auto jump=[&](unsigned char*& at,std::uintptr_t target){*at++=0xe9;imm(at,target-reinterpret_cast<std::uintptr_t>(at)-4);};
    auto* ordinary=image+0x1082a;jump(ordinary,reinterpret_cast<std::uintptr_t>(&OrdinaryFixture));
    auto* at=image+0x6659;jump(at,reinterpret_cast<std::uintptr_t>(&Followup));
    at=image+0x9bbf0;
    byte(at,{0x55,0x8b,0xec});
    for(unsigned char offset:std::array<unsigned char,7>{0x20,0x1c,0x18,0x14,0x10,0x0c,0x08}){byte(at,{0xff,0x75,offset});}
    *at++=0xb8;imm(at,reinterpret_cast<std::uintptr_t>(&Use));byte(at,{0xff,0xd0,0x83,0xc4,0x1c});
    jump(at,base+0x9bf04);
    at=image+0x9bf04;*at++=0xe8;imm(at,base+0x9c710-reinterpret_cast<std::uintptr_t>(at)-4);
    byte(at,{0x5d,0xc3});
    at=image+0x9c710;byte(at,{0x55,0x8b,0xec,0x53,0x56,0x57,0x83,0xec,0x48});
    byte(at,{0x8b,0x45,0x00,0x8b,0x50,0x0c,0x89,0x55,0xb8,0x8b,0x70,0x10,0x8b,0x58,0x14});
    *at++=0xbf;imm(at,reinterpret_cast<std::uintptr_t>(definition.data()));
    *at++=0xb9;imm(at,reinterpret_cast<std::uintptr_t>(sender));
    *at++=0xa1;imm(at,reinterpret_cast<std::uintptr_t>(&current_message));*at++=0x50;jump(at,base+0x9d3d4);
    at=image+0x9d3d9;byte(at,{0x8b,0x55,0xb8,0x52,0x57,0x53,0x56});
    at=image+0x9d3e5;byte(at,{0x83,0xc4,0x10,0x8d,0x65,0xf4,0x5f,0x5e,0x5b,0x5d,0xc3});
    native_use=reinterpret_cast<pw::Use>(base+0x9bbf0);
    pw::Send sender_call=reinterpret_cast<pw::Send>(&Send);
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
    if (!probe::Prepare(argc,argv,image)) { return 2; }
    sender_call=reinterpret_cast<pw::Send>(base+0x7f4da0);
#endif
    DWORD old{}; Check(VirtualProtect(image,0x800000,PAGE_EXECUTE_READ,&old)!=0,"fixture executable");
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
    probe::Learned(image);
#endif
    if(argc==4 && std::strcmp(argv[1],"image-admission")==0) {
        image_digest=argv[2]; verified_image=base;
        const bool allowed=std::strcmp(argv[3],"allow")==0;
        SetLastError(42);
        Check(pw::Start(base)==allowed,"exact power image admission");
        Check(GetLastError()==42,"power startup preserves caller LastError");
        Check(pw::Ready()==allowed,"only admitted power image publishes readiness");
        Check(verification_calls==(allowed?1U:0U),"unknown power image rejected before loaded-image verification");
        if(!allowed) {
            Check(image[0x9d3d4]==0xe8 && image[0x9d3e0]==0xe8,"denied power image never installs hooks");
        }
        return failures?1:0;
    }
    if(argc==2 && std::strcmp(argv[1],"partial-install")==0) {
        Check(!pw::StartBound(base,sender_call,Followup,PartialInstall)&&!pw::Ready(),"partial install never ready");
        const auto prior=sends;const float point[3]{};native_use(428918601,20,actor.data(),target.data(),point,pw::Key{});Check(sends==prior+1,"partial owned site retains pinned passthrough handler");
        Check(image[0x9d3d4]==0xcc && image[0x9d3e0]==0xe8,"partial installation owns only successful byte");
        return failures?1:0;
    }
    Check(pw::StartBound(base,sender_call,Followup),"atomic interception install");
    pw::Receipt receipt{};outer_receipt=&receipt;
    pw::Context context{base,reinterpret_cast<std::uintptr_t>(actor.data()),reinterpret_cast<std::uintptr_t>(target.data()),base+0x1600000,base+0x1600100,local,victim,428918601,Current,QueueCurrent,nullptr,&receipt};
    const auto reset=[&] { references=2;current_message=message.data(); message={};message[0]=static_cast<std::uint32_t>(base+0x1155fd8);message[0x80/4]=context.power_id;message[0xa4/4]=1;message[0x88/4]=local[0];message[0x8c/4]=local[1];message[0x90/4]=context.RecipientKey()[0];message[0x94/4]=context.RecipientKey()[1];current=true;queue_current=true;fault_send=false;fault_followup=false;seh_send=false;seh_followup=false;corrupt_key=false;revoke_during_use=false;receipt={};actor_mode=1;stance_reads=stance_toggles=0;deny_stance=revoke_stance=revoke_mode_read=fault_stance=seh_stance=false;replaced_target_key=nullptr;availability=pw::Availability::ready; };
    reset(); Check(Guarded(context),"normal power invocation");Check(receipt.result==pw::Result::queued && receipt.native_entered && receipt.send_observed && receipt.append_observed && receipt.followup_entered,"queued receipt preserves all boundaries");
    Check(receipt.initiation_epoch && receipt.initiation_epoch==pw::InitiationEpoch(),"ordinary owned followup captures mutation provenance");
    Check(receipt.observation.use_called&&receipt.observation.use_returned
        &&receipt.observation.definition_known&&receipt.observation.state_known
        &&receipt.observation.actor_mode==2&&receipt.observation.state_aux==3
        &&receipt.observation.initiation_state==5,"copied pre-entry fields and normal return remain diagnostics");
    {
        reset();const auto saved_use=native_use;native_use=RefusedUse;
        Check(Guarded(context)&&receipt.native_entered&&!receipt.append_observed
            &&receipt.observation.use_called&&receipt.observation.use_returned&&!receipt.observation.use_value
            &&GetLastError()==7654,"false native return remains entered uncertainty with exact diagnostic and LastError");
        native_use=saved_use;
        reset();actor[0xad0/4]=0x10000;
        Check(Guarded(context)&&receipt.result==pw::Result::queued&&!receipt.observation.state_known,
            "unreadable optional state never blocks ordinary queue");
        actor[0xad0/4]=reinterpret_cast<std::uint32_t>(diagnostic_state.data());
    }
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
    Check(references==1,"real native sender preserves exactly one caller-owned reference");
#endif
    for(auto nested_id:{428918601U,428918602U}) {
        reset();unrelated_power=nested_id;reenter_send=true;Check(Guarded(context)&&receipt.result==pw::Result::queued,"sender reentry preserves scoped submission");Check(!receipt.initiation_epoch,"nested native work invalidates instant followup provenance");
        reset();unrelated_power=nested_id;reenter_followup=true;Check(Guarded(context)&&receipt.result==pw::Result::queued,"followup reentry preserves scoped submission");Check(!receipt.initiation_epoch,"nested native work invalidates instant followup provenance");
    }
    // Positive readiness refusal cannot call stance, native Use, sender or followup.
    definition[0x1f0/4]=1;
    for(auto reason:{pw::Availability::reuse_blocked,pw::Availability::global_recovery,pw::Availability::unknown}) {
        reset();availability=reason;const auto before_uses=uses,before_send=sends,before_followup=followups;
        Check(Guarded(context)&&!receipt.native_entered&&!receipt.append_observed
            &&receipt.availability==reason&&uses==before_uses&&sends==before_send
            &&followups==before_followup&&!stance_reads&&!stance_toggles,"readiness refusal is side-effect free");
    }
    for(unsigned change=0;change<2;++change) {
        reset();pw::Scope scope(context);
        Check(!scope.AdmitAvailability(pw::Availability::reuse_blocked,pw::InitiationEpoch()),"refusal never enters");
        if(change==0) { current=false; } else { pw::AdvanceEpoch(); }
        const auto refused=scope.Finish();
        Check(refused.availability==pw::Availability::unknown&&!refused.native_entered
            &&!refused.availability_epoch,"late authority/epoch loss cannot publish actionable refusal");
    }
    reset();
    {
        pw::Scope scope(context);const auto before=pw::InitiationEpoch();pw::AdvanceEpoch();
        Check(!scope.AdmitAvailability(pw::Availability::reuse_blocked,before)
            &&scope.Finish().availability==pw::Availability::unknown,"capture epoch never refreshed after native callback");
    }
    definition[0x1f0/4]=0;reset();
    const auto total=uses;
    for(auto category:{2U,5U,99U}) {reset();definition[0x204/4]=category;Check(Guarded(context)&&!receipt.native_entered,"unsupported category rejects before entry");}definition[0x204/4]=0;
    for(auto mode:{2U,3U}) {reset();definition[0x1a8/4]=mode;Check(Guarded(context)&&!receipt.native_entered,"self redirect rejects object action");}definition[0x1a8/4]=1;
    reset();learned_rank=0;Check(Guarded(context)&&!receipt.native_entered,"unlearned rejects before entry");learned_rank=20;
    Check(uses==total,"rejected native categories never invoke mutating path");
    context.target_mode=pw::TargetMode::self;definition[0x1a8/4]=2;
    reset();Check(Guarded(context)&&receipt.result==pw::Result::queued,"self power queues through qualified native route");
    Check(last_actor==actor.data()&&last_target==actor.data()&&context.target==reinterpret_cast<std::uintptr_t>(target.data()),"actor recipient does not replace engagement target");
    for(auto mode:{0U,1U,3U,10U}) {reset();definition[0x1a8/4]=mode;Check(Guarded(context)&&!receipt.native_entered,"self action rejects other target modes before entry");}
    definition[0x1a8/4]=2;
    for(auto delivery:{1U,2U,99U}) {reset();definition[0x1b4/4]=delivery;Check(Guarded(context)&&!receipt.native_entered,"self action rejects unqualified delivery");}
    definition[0x1b4/4]=0;
    reset();message[0x90/4]=victim[0];message[0x94/4]=victim[1];auto self_sends=sends;
    Check(Guarded(context)&&sends==self_sends&&!receipt.append_observed,"self power rejects engagement recipient in native ticket");
    reset();revoke_during_use=true;self_sends=sends;
    Check(Guarded(context)&&sends==self_sends&&receipt.native_entered&&!receipt.append_observed,"self power still checks engagement authority after native entry");
    reset();++target[6];self_sends=sends;
    Check(Guarded(context)&&sends==self_sends&&!receipt.append_observed,"self recipient cannot hide engagement object replacement");--target[6];
    reset();queue_current=false;auto self_effects=followups;
    Check(Guarded(context)&&receipt.native_entered&&!receipt.append_observed&&followups==self_effects,"self power revoked append suppresses followup");
    reset();seh_followup=true;Check(!Guarded(context)&&receipt.append_observed&&receipt.result==pw::Result::uncertain&&!pw::active,"self power SEH retains queue history and restores TLS");
    for(auto nested_id:{428918601U,428918602U}) {
        reset();unrelated_power=nested_id;reenter_send=true;Check(Guarded(context)&&receipt.result==pw::Result::queued,"self sender reentry retains exact frame");Check(!receipt.initiation_epoch,"nested native work invalidates instant followup provenance");
        reset();unrelated_power=nested_id;reenter_followup=true;Check(Guarded(context)&&receipt.result==pw::Result::queued,"self followup reentry retains exact frame");Check(!receipt.initiation_epoch,"nested native work invalidates instant followup provenance");
    }
    // Explicit actor authority is independent of selection and target lifetime.
    const auto engagement_context=context;
    context.authority=pw::Authority::actor;context.target=0;context.target_key={};
    reset();Check(Guarded(context)&&receipt.result==pw::Result::queued,
        "actor-only self power queues without target object");
    reset();++target[6];Check(Guarded(context)&&receipt.append_observed,
        "unrelated target replacement does not revoke actor-only power");--target[6];
    reset();context.target=engagement_context.target;
    Check(Guarded(context)&&!receipt.native_entered,"actor authority rejects embedded target");context.target=0;
    reset();context.target_key=victim;
    Check(Guarded(context)&&!receipt.native_entered,"actor authority rejects target key");context.target_key={};
    reset();context.target_mode=pw::TargetMode::engagement_object;
    Check(Guarded(context)&&!receipt.native_entered,"actor authority cannot send targeted power");
    context=engagement_context;
    // Native definition +1f0, not category/self, owns the stance prerequisite.
    definition[0x1f0/4]=1;
    reset();auto stance_uses=uses;
    Check(Guarded(context)&&receipt.result==pw::Result::queued&&stance_toggles==1
        &&actor_mode==2&&uses==stance_uses+1,"peace mode enters combat before one self power");
    for(auto mode:{2U,3U,0x7fffffffU}) {
        reset();actor_mode=mode;stance_uses=uses;
        Check(Guarded(context)&&receipt.result==pw::Result::queued&&stance_toggles==0
            &&actor_mode==mode&&uses==stance_uses+1,"eligible signed native modes never toggle");
    }
    for(auto mode:{0U,0xffffffffU,0x80000000U}) {
        reset();actor_mode=mode;stance_uses=uses;
        Check(Guarded(context)&&receipt.native_entered&&!receipt.append_observed
            &&stance_toggles==0&&uses==stance_uses,"ineligible signed mode never invokes power");
    }
    for(auto required:{2U,3U}) {
        definition[0x1f0/4]=required;reset();stance_uses=uses;
        Check(Guarded(context)&&receipt.result==pw::Result::queued&&stance_reads==(required==2?1U:0U)
            &&stance_toggles==0&&actor_mode==1&&uses==stance_uses+1,
            "peace-only and either-mode powers preserve ordinary native behavior");
    }
    // Shared native entry covers both the actor-only preparation path and a
    // context-bound self power, which has no selector publication prerequisite.
    definition[0x1f0/4]=2;
    for(const auto authority:{pw::Authority::engagement,pw::Authority::actor}) {
        context=engagement_context;context.authority=authority;
        if(authority==pw::Authority::actor){context.target=0;context.target_key={};}
        for(auto mode:{2U,3U,0x7fffffffU}) {
            reset();actor_mode=mode;const auto before_uses=uses,before_sends=sends,before_followups=followups;
            Check(Guarded(context)&&!receipt.native_entered&&!receipt.append_observed
                &&receipt.availability==pw::Availability::stance_ineligible
                &&receipt.availability_epoch==pw::InitiationEpoch()&&stance_reads==1&&!stance_toggles
                &&uses==before_uses&&sends==before_sends&&followups==before_followups,
                "combat peace-only refusal creates no native side effect or pending entry");
        }
        for(auto mode:{1U,0U,0xffffffffU,0x80000000U}) {
            reset();actor_mode=mode;const auto before_uses=uses;
            Check(Guarded(context)&&receipt.result==pw::Result::queued&&uses==before_uses+1
                &&stance_reads==1&&!stance_toggles,"native signed peace predicate is unchanged without a toggle or timer");
        }
    }
    context=engagement_context;
    definition[0x1f0/4]=3;reset();actor_mode=2;stance_uses=uses;
    Check(Guarded(context)&&receipt.result==pw::Result::queued&&uses==stance_uses+1
        &&!stance_reads&&!stance_toggles,"either-mode buffs remain admitted in combat without stance changes");
    definition[0x1f0/4]=2;
    reset();combat_during_availability=true;stance_uses=uses;
    Check(Guarded(context)&&!receipt.native_entered&&receipt.availability==pw::Availability::stance_ineligible
        &&uses==stance_uses&&!stance_toggles,"entry observes mode change after resource readiness");
    combat_during_availability=false;
    for(unsigned change:{1U,2U}) {
        reset();actor_mode=2;revoke_mode_read=change==1;epoch_during_mode_read=change==2;stance_uses=uses;
        Check(Guarded(context)&&!receipt.native_entered&&receipt.availability==pw::Availability::unknown
            &&!receipt.availability_epoch&&uses==stance_uses&&!stance_toggles,
            "mode callback identity or initiation-epoch loss cannot publish a qualified refusal");
        epoch_during_mode_read=false;
    }
    definition[0x1f0/4]=1;
    reset();deny_stance=true;stance_uses=uses;
    Check(Guarded(context)&&receipt.native_entered&&receipt.result==pw::Result::uncertain
        &&!receipt.append_observed&&uses==stance_uses&&stance_toggles==1,
        "rejected native stance cannot queue or claim no entry");
    reset();revoke_mode_read=true;stance_uses=uses;
    Check(Guarded(context)&&receipt.native_entered&&!receipt.append_observed
        &&uses==stance_uses&&stance_toggles==0,"current guard wins before stance mutation");
    reset();revoke_stance=true;stance_uses=uses;
    Check(Guarded(context)&&receipt.native_entered&&!receipt.append_observed
        &&uses==stance_uses&&stance_toggles==1,"reentrant owner revoke stops after stance");
    reset();replaced_target_key=&target[6];stance_uses=uses;
    Check(Guarded(context)&&receipt.native_entered&&!receipt.append_observed
        &&uses==stance_uses,"self stance cannot bypass retained NPC identity");--target[6];
    reset();seh_stance=true;stance_uses=uses;
    Check(!Guarded(context)&&receipt.native_entered&&!receipt.append_observed
        &&uses==stance_uses&&!pw::active,"stance SEH preserves entry and restores scope");
    reset();fault_stance=true;stance_uses=uses;
    try{Run(context);Check(false,"stance C++ fault expected");}catch(const std::runtime_error&){}
    Check(receipt.native_entered&&!receipt.append_observed&&uses==stance_uses&&!pw::active,
        "stance C++ fault retains native entry and unlinks scope");
    definition[0x1f0/4]=0;
    context.target_mode=pw::TargetMode::engagement_object;definition[0x1a8/4]=1;
    reset();queue_current=false;auto before=followups;Check(Guarded(context)&&receipt.result==pw::Result::uncertain&&!receipt.append_observed&&followups==before,"denied append suppresses effects and preserves entry");
    reset();corrupt_key=true;before=sends;Check(Guarded(context)&&sends==before&&!receipt.append_observed,"wrong native target key consumed before send");
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
    // Real native sender ownership has been exercised above. Its foreign EH
    // metadata cannot be unwound in an arena; pre-send SEH uses the fixture
    // call-through, while post-queue SEH below follows the real sender return.
    pw::original_send=reinterpret_cast<pw::Send>(&Send);
#endif
    reset();seh_send=true;Check(!Guarded(context)&&receipt.native_entered&&!receipt.append_observed,"SEH before append retains partial native entry");Check(pw::active==nullptr,"SEH explicitly restores TLS");
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
    pw::original_send=sender_call;
#endif
    reset();seh_followup=true;Check(!Guarded(context)&&receipt.append_observed&&receipt.followup_entered&&receipt.result==pw::Result::uncertain,"SEH preserves queued history");Check(pw::active==nullptr,"followup SEH restores TLS");
    Check(receipt.observation.use_called&&!receipt.observation.use_returned&&!receipt.observation.use_value,
        "SEH never invents a normal Use return");
    reset();fault_followup=true;try{Run(context);Check(false,"C++ fault expected");}catch(const std::runtime_error&){}Check(!pw::active&&receipt.append_observed,"C++ unwind preserves queue fact");
    reset();before=sends;const float point[3]{};native_use(428918601,20,actor.data(),target.data(),point,pw::Key{});Check(sends==before+1&&!pw::active,"unscoped native calls pass through after faults");
    reset();current=false;before=lookups;Check(Guarded(context)&&lookups==before&&!receipt.native_entered,"revoked owner prevents native lookup");
    reset();{
        pw::Scope unbound_frame(context);Check(unbound_frame.Enter(reinterpret_cast<std::uintptr_t>(definition.data()),20),"entered scope without bridge");
        const auto before_receipt=receipt;unrelated=true;
        const float position[3]{};native_use(428918601,20,actor.data(),target.data(),position,pw::Key{});unrelated=false;
        Check(receipt.result==before_receipt.result&&!receipt.send_observed&&!receipt.append_observed&&!receipt.followup_entered,"Scope Enter alone cannot authorize native frame");
    }
    reset();{pw::Scope outer(context);pw::Scope inner(context);(void)outer.Finish();Check(!inner.CanEnter(),"out of order scope finish revokes descendants");}Check(!pw::active,"out of order scopes unlink");
    reset();std::array<std::uint8_t,5> disk=pw::sites[0].bytes,code=disk;code[0]=0xcc;
    // A truncated span cannot authorize only one of the owned callsites.
    Check(!pw::NormalizeOwnedCode(base,0x9d3d4,code,disk),"normalization rejects incomplete owned image");
    const auto first=pw::sites[6].rva; // Lowest observed callsite.
    const auto last=pw::sites[5].rva+5;
    std::vector<std::uint8_t> whole_disk(last-first),whole_code;
    for(const auto& site:pw::sites) { std::copy(site.bytes.begin(),site.bytes.end(),whole_disk.begin()+site.rva-first); }
    const auto patched=[&] { whole_code=whole_disk; for(const auto& site:pw::sites) { whole_code[site.rva-first]=0xcc; } };
    patched();Check(pw::NormalizeOwnedCode(base,first,whole_code,whole_disk)&&whole_code==whole_disk,"normalization accepts all owned exact sites");
    patched();whole_code[pw::sites[0].rva-first+1]^=1;
    Check(!pw::NormalizeOwnedCode(base,first,whole_code,whole_disk),"normalization rejects foreign displacement");
    // Every added site preserves CALL machine state and advances provenance; ordinary Use enters its qualified wrapper.
    for(std::size_t i=2;i<pw::sites.size();++i) {
        DWORD stack[4]{};CONTEXT c{};EXCEPTION_RECORD r{};EXCEPTION_POINTERS e{&r,&c};
        const auto& site=pw::sites[i];r.ExceptionCode=EXCEPTION_BREAKPOINT;r.ExceptionAddress=image+site.rva;
        c.Eip=static_cast<DWORD>(base+site.rva);c.Esp=reinterpret_cast<DWORD>(stack+2);
        c.Eax=11;c.Ebx=22;c.Ecx=33;c.Edx=44;c.Ebp=55;c.Esi=66;c.Edi=77;c.EFlags=0x246;
        const auto epoch_before=pw::InitiationEpoch();SetLastError(1234);
        Check(pw::Trap(&e)==EXCEPTION_CONTINUE_EXECUTION,"qualified protocol CALL handled");
        std::int32_t displacement{};std::memcpy(&displacement,site.bytes.data()+1,4);
        Check(c.Eip==(i<=5?reinterpret_cast<DWORD>(&pw::OrdinaryUseHook):base+site.rva+5+displacement) && c.Esp==reinterpret_cast<DWORD>(stack+1)
            && stack[1]==base+site.rva+5 && c.Eax==11&&c.Ebx==22&&c.Ecx==33&&c.Edx==44
            &&c.Ebp==55&&c.Esi==66&&c.Edi==77&&c.EFlags==0x246&&GetLastError()==1234,
            "protocol CALL preserves register flags LastError and native return");
        Check(pw::InitiationEpoch()==epoch_before+1,"foreign protocol event invalidates prior provenance");
    }
    SetLastError(1234);ordinary_nested=true;
    Check(OrdinaryCall()&&!pw::NativeUseInFlight()&&GetLastError()==4321,"ordinary wrapper preserves return and native LastError");
    ordinary_fault=true;Check(OrdinarySeh()&&!pw::NativeUseInFlight(),"ordinary SEH restores in-flight state");ordinary_fault=false;
    ordinary_throw=true;bool caught=false;try{(void)OrdinaryCall();}catch(int value){caught=value==42;}
    Check(caught&&!pw::NativeUseInFlight(),"ordinary C++ unwind restores in-flight state");ordinary_throw=false;
    pw::native_use_in_flight=true;
    std::thread independent([] { Check(!pw::NativeUseInFlight()&&OrdinaryCall()&&!pw::NativeUseInFlight(),"ordinary in-flight is thread-local"); });independent.join();
    Check(pw::NativeUseInFlight(),"other thread preserves parent in-flight state");pw::native_use_in_flight=false;
    InterlockedExchange64(&pw::initiation_epoch,MAXLONGLONG-1);pw::AdvanceEpoch();
    Check(!pw::InitiationEpoch(),"epoch saturation disables allowance");pw::AdvanceEpoch();
    Check(!pw::InitiationEpoch(),"saturated epoch never wraps into an old request");
    CONTEXT machine{};EXCEPTION_RECORD record{};EXCEPTION_POINTERS exception{&record,&machine};record.ExceptionCode=EXCEPTION_BREAKPOINT;record.ExceptionAddress=image+0x9d3d4;machine.Eip=static_cast<DWORD>(base+0x9d3d6);Check(pw::Trap(&exception)==EXCEPTION_CONTINUE_SEARCH,"foreign EIP is not swallowed");
    std::printf("Power entry/observer failures: %d\n",failures);
    // Installed hooks and handler intentionally live until process exit.
    return failures?1:0;
}
