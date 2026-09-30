#include "combat_power_observer.cpp"
#include "combat_power_entry.cpp"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
namespace pw = wonderbane::extension::combat::power;
namespace sb = wonderbane::extension::combat::submission;
namespace {
int failures{};
int references = 2;
void Check(bool ok, const char* label) { if (!ok) { ++failures; std::fprintf(stderr, "%s\n", label); } }
sb::PowerAppendObserver registered{};
unsigned sends{}, appends{}, followups{}, releases{}, uses{}, lookups{};
bool current = true, queue_current = true, fault_send = false, fault_followup = false;
bool seh_send = false, seh_followup = false, corrupt_key = false;
int learned_rank = 20;
unsigned installation_steps{};
bool PartialInstall(pw::Site& site) noexcept { return ++installation_steps==1 && pw::InstallByte(site); }
std::array<std::uint32_t,0xb0/4> message{};
std::array<std::uint32_t,0x300/4> definition{};
void* queue{};
std::uint32_t* current_message=message.data();
bool unrelated{}, reenter_send{}, reenter_followup{};
std::uint32_t unrelated_power=428918601;
pw::Receipt* outer_receipt{};
void* last_actor{};void* last_target{};
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
bool __cdecl Use(std::uint32_t id, int rank, void* actor, void* target, const float* position, pw::Key key) {
    ++uses; last_actor=actor;last_target=target;Check((id == 428918601 || unrelated) && rank == std::min(learned_rank,9999), "native learned rank");
    Check(key == pw::Key{} && position[0] == 0 && position[1] == 0 && position[2] == 0, "zero key preserves native target validation");
    current_message[0x80/4]=id;
    current_message[0x84/4] = static_cast<std::uint32_t>(rank);
    if (corrupt_key) { ++current_message[0x90/4]; }
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
void Run(const pw::Context& c) { pw::Scope scope(c); (void)pw::InvokeBound(scope, {Definition,reinterpret_cast<pw::Rank>(&Rank),native_use}); }
bool Guarded(const pw::Context& c) {
    pw::Boundary boundary;
    __try { __try { Run(c); } __finally { boundary.Restore(); } }
    __except(GetExceptionCode()==0xe0420201 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { return false; }
    return true;
}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return false; }
namespace movement { bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; } }
namespace combat::submission {
bool RegisterPowerAppendObserver(const PowerAppendObserver& observer) noexcept { registered = observer; return true; }
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
    std::array<std::uint32_t,0x700/4> actor{}, target{};
    const pw::Key local{123,53}, victim{456,42};
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
    if(argc==2 && std::strcmp(argv[1],"partial-install")==0) {
        Check(!pw::StartBound(base,sender_call,Followup,PartialInstall)&&!pw::Ready(),"partial install never ready");
        const auto prior=sends;const float point[3]{};native_use(428918601,20,actor.data(),target.data(),point,pw::Key{});Check(sends==prior+1,"partial owned site retains pinned passthrough handler");
        Check(image[0x9d3d4]==0xcc && image[0x9d3e0]==0xe8,"partial installation owns only successful byte");
        return failures?1:0;
    }
    Check(pw::StartBound(base,sender_call,Followup),"atomic interception install");
    pw::Receipt receipt{};outer_receipt=&receipt;
    pw::Context context{base,reinterpret_cast<std::uintptr_t>(actor.data()),reinterpret_cast<std::uintptr_t>(target.data()),base+0x1600000,base+0x1600100,local,victim,428918601,Current,QueueCurrent,nullptr,&receipt};
    const auto reset=[&] { references=2;current_message=message.data(); message={};message[0]=static_cast<std::uint32_t>(base+0x1155fd8);message[0x80/4]=context.power_id;message[0xa4/4]=1;message[0x88/4]=local[0];message[0x8c/4]=local[1];message[0x90/4]=victim[0];message[0x94/4]=victim[1];current=true;queue_current=true;fault_send=false;fault_followup=false;seh_send=false;seh_followup=false;corrupt_key=false;receipt={}; };
    reset(); Check(Guarded(context),"normal power invocation");Check(receipt.result==pw::Result::queued && receipt.native_entered && receipt.send_observed && receipt.append_observed && receipt.followup_entered,"queued receipt preserves all boundaries");
#if defined(WONDERBANE_POWER_PRIVATE_PROBE)
    Check(references==1,"real native sender preserves exactly one caller-owned reference");
#endif
    for(auto nested_id:{428918601U,428918602U}) {
        reset();unrelated_power=nested_id;reenter_send=true;Check(Guarded(context)&&receipt.result==pw::Result::queued,"sender reentry preserves scoped submission");
        reset();unrelated_power=nested_id;reenter_followup=true;Check(Guarded(context)&&receipt.result==pw::Result::queued,"followup reentry preserves scoped submission");
    }
    const auto total=uses;
    for(auto category:{2U,5U,99U}) {reset();definition[0x204/4]=category;Check(Guarded(context)&&!receipt.native_entered,"unsupported category rejects before entry");}definition[0x204/4]=0;
    for(auto mode:{2U,3U}) {reset();definition[0x1a8/4]=mode;Check(Guarded(context)&&!receipt.native_entered,"self redirect rejects object action");}definition[0x1a8/4]=1;
    reset();learned_rank=0;Check(Guarded(context)&&!receipt.native_entered,"unlearned rejects before entry");learned_rank=20;
    Check(uses==total,"rejected native categories never invoke mutating path");
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
    // A truncated span cannot authorize only one of two owned callsites.
    Check(!pw::NormalizeOwnedCode(base,0x9d3d4,code,disk),"normalization rejects incomplete owned image");
    std::array<std::uint8_t,0x11> whole_disk{},whole_code{};
    std::copy(pw::sites[0].bytes.begin(),pw::sites[0].bytes.end(),whole_disk.begin());
    std::copy(pw::sites[1].bytes.begin(),pw::sites[1].bytes.end(),whole_disk.begin()+0xc);
    whole_code=whole_disk;whole_code[0]=0xcc;whole_code[0xc]=0xcc;
    Check(pw::NormalizeOwnedCode(base,0x9d3d4,whole_code,whole_disk)&&whole_code==whole_disk,"normalization accepts only owned exact sites");
    whole_code=whole_disk;whole_code[0]=0xcc;whole_code[0xc]=0xcc;whole_code[1]^=1;
    Check(!pw::NormalizeOwnedCode(base,0x9d3d4,whole_code,whole_disk),"normalization rejects foreign displacement");
    CONTEXT machine{};EXCEPTION_RECORD record{};EXCEPTION_POINTERS exception{&record,&machine};record.ExceptionCode=EXCEPTION_BREAKPOINT;record.ExceptionAddress=image+0x9d3d4;machine.Eip=static_cast<DWORD>(base+0x9d3d6);Check(pw::Trap(&exception)==EXCEPTION_CONTINUE_SEARCH,"foreign EIP is not swallowed");
    std::printf("Power entry/observer failures: %d\n",failures);
    // Installed hooks and handler intentionally live until process exit.
    return failures?1:0;
}
