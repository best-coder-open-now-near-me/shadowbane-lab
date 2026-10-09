#include "actor_effects_native.cpp"
#include <cstdio>
#include <stdexcept>
#include <thread>
#include <atomic>

// Explicit unit seams: this arena is not a qualified executable. Exact-image
// qualification remains the independent private-image probe's responsibility.
namespace bootstrap_fixture {
bool identity_ready = false, image_valid = true;
std::uintptr_t verified_image{};
unsigned image_checks{};
const char* digest="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d";
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char* digest) noexcept {
    return bootstrap_fixture::identity_ready && digest
        && std::strcmp(digest,bootstrap_fixture::digest)==0;
}
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t& verified) noexcept {
    ++bootstrap_fixture::image_checks;
    verified=bootstrap_fixture::verified_image;
    return bootstrap_fixture::image_valid;
}
}
}
namespace e = wonderbane::extension::actor_effects;
namespace {
unsigned failures{}, calls{};
void Check(bool ok, const char* label) { if (!ok) { ++failures; std::fprintf(stderr,"%s\n",label); } }
unsigned char* image{};
alignas(4) std::array<unsigned char,0xe00> actor{};
alignas(4) std::array<unsigned char,0x78> record{};
alignas(4) std::array<unsigned char,0x60> descriptor{};
alignas(4) std::array<unsigned char,0x20> action{};
std::array<e::Pair,2> entries{};
e::Context context{};
bool current = true, mutate_callback = false;
template<class T> void Put(std::uintptr_t at, const T& value) { std::memcpy(reinterpret_cast<void*>(at),&value,sizeof(value)); }
std::uintptr_t Address(auto& object) { return reinterpret_cast<std::uintptr_t>(object.data()); }
bool Current(void*) noexcept { if (mutate_callback) { e::Advance(); } return current; }
bool OtherCurrent(void*) noexcept { return current; }
void Fill() {
    actor.fill(0); record.fill(0); descriptor.fill(0); action.fill(0); entries={};
    const auto b=reinterpret_cast<std::uintptr_t>(image),a=Address(actor),d=Address(descriptor);
    context={b,a,{4050960,53},1,Current,nullptr}; current=true; mutate_callback=false;
    Put(b+0x16a2d98,static_cast<std::uint32_t>(a)); Put(a,static_cast<std::uint32_t>(b+0x114165c));
    Put(a+0x588,static_cast<std::uint32_t>(b+0x11415fc)); Put(a+0x18,context.actor_key);
    Put(d,static_cast<std::uint32_t>(b+0x1147930)); Put(d+0x14,std::uint32_t{123});
    Put(Address(action),static_cast<std::uint32_t>(b+0x1148b48)); Put(Address(action)+0x1c,std::uint32_t{456});
    Put(Address(record),static_cast<std::uint32_t>(d)); Put(Address(record)+0x14,static_cast<std::uint32_t>(d+0x5c));
    Put(Address(record)+0x10,std::uint32_t{35}); Put(Address(record)+0x38,std::uint32_t{429021400});
    Put(Address(record)+0x68,static_cast<std::uint32_t>(Address(action)));
    entries[0]={123,static_cast<std::uint32_t>(Address(record))};
    const auto p=static_cast<std::uint32_t>(Address(entries));
    Put(a+0x58c,e::Vector{p,p+8,p+16});
}
std::uint32_t __fastcall OriginalAdd(void* self,void*,std::uint32_t value) {
    Check(self==reinterpret_cast<void*>(context.actor+0x588) && value==77,"add exact ECX/stack argument");
    Check(GetLastError()==1234,"wrapper preserves incoming LastError");
    ++calls; e::Snapshot blocked; Check(e::Capture(context,blocked)==e::Unknown::mutation_active,"reentrant capture rejects intermediate mutation");
    SetLastError(5678); return 987;
}
std::uint32_t __fastcall OriginalRemove(void* self,void*,std::uint32_t a,std::uint32_t b) {
    Check(self==reinterpret_cast<void*>(context.actor+0x588) && a==7 && b==8,"remove exact ECX/two arguments");
    ++calls;SetLastError(4321);return 654;
}
std::uint32_t __fastcall OriginalNoArgs(void* self,void*) {
    Check(self==reinterpret_cast<void*>(context.actor),"zero-argument wrapper exact ECX");++calls;return 321;
}
std::uint32_t __fastcall OriginalEquipment(void* self,void*,std::uint32_t value) {
    Check(self==reinterpret_cast<void*>(context.actor) && value==99,"equipment ECX/argument");++calls;return 222;
}
std::uint32_t __fastcall ThrowCpp(void*,void*,std::uint32_t) { throw std::runtime_error("native fixture"); }
std::uint32_t __fastcall ThrowSeh(void*,void*,std::uint32_t) { RaiseException(0xe0001234,0,0,nullptr);return 0; }
bool InvokeSeh() {
    __try { (void)e::AddHook(reinterpret_cast<void*>(context.actor),nullptr,0); }
    __except (GetExceptionCode()==0xe0001234 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
bool Partial(e::Site& site) noexcept { return site.rva==0x49fbb2 ? false : e::InstallSite(site); }
void Prepare() {
    image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x16b0000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    Check(image!=nullptr,"image arena allocated"); if(!image){return;}
    const auto b=reinterpret_cast<std::uintptr_t>(image);
    for(const auto& site:e::sites){std::memcpy(image+site.rva,site.bytes.data(),5);}
    for(const auto& slot:e::slots){Put(b+slot.rva,static_cast<std::uint32_t>(b+slot.original_rva));}
    IMAGE_DOS_HEADER dos{};dos.e_magic=IMAGE_DOS_SIGNATURE;dos.e_lfanew=0x80;Put(b,dos);
    IMAGE_NT_HEADERS32 nt{};nt.Signature=IMAGE_NT_SIGNATURE;nt.FileHeader.Machine=IMAGE_FILE_MACHINE_I386;
    nt.OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR32_MAGIC;nt.OptionalHeader.AddressOfEntryPoint=0x8d8c4a;
    nt.OptionalHeader.NumberOfRvaAndSizes=IMAGE_NUMBEROF_DIRECTORY_ENTRIES;Put(b+0x80,nt);
    std::memcpy(image+0x1140e70,wonderbane::extension::movement::bootstrap_replacement_6.data(),113);
    Fill();
}
void TestTrap(const e::Site& site) {
    std::array<DWORD,4> stack{}; CONTEXT machine{};EXCEPTION_RECORD record_exception{};
    machine.Eip=static_cast<DWORD>(context.image+site.rva);machine.Esp=static_cast<DWORD>(Address(stack)+8);
    machine.Eax=11;machine.Ebx=12;machine.Ecx=13;machine.Edx=14;machine.Ebp=15;machine.Esi=16;machine.Edi=17;machine.EFlags=0x202;
    const auto original=machine;record_exception.ExceptionCode=EXCEPTION_BREAKPOINT;
    record_exception.ExceptionAddress=reinterpret_cast<void*>(machine.Eip);EXCEPTION_POINTERS exception{&record_exception,&machine};
    SetLastError(789);Check(e::Trap(&exception)==EXCEPTION_CONTINUE_EXECUTION,"each owned CALL trap accepted");
    Check(machine.Esp==original.Esp-4 && stack[1]==original.Eip+5,"CALL trap exact native return stack");
    Check(machine.Eip==reinterpret_cast<DWORD>(site.rebuild?reinterpret_cast<void*>(&e::RebuildHook):reinterpret_cast<void*>(&e::EquipmentHook)),"CALL trap exact wrapper");
    Check(machine.Eax==original.Eax && machine.Ebx==original.Ebx && machine.Ecx==original.Ecx && machine.Edx==original.Edx
        && machine.Ebp==original.Ebp && machine.Esi==original.Esi && machine.Edi==original.Edi && machine.EFlags==original.EFlags
        && GetLastError()==789,"trap preserves registers flags and LastError");
}
}
int main(int argc,char** argv) {
    if(argc==2 && std::strcmp(argv[1],"prepared14")==0){bootstrap_fixture::digest="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903";}
    if(argc==2 && std::strcmp(argv[1],"prepared15")==0){bootstrap_fixture::digest="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437";}
    if(argc==2 && std::strcmp(argv[1],"prepared16")==0){bootstrap_fixture::digest="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c";}
    Prepare();if(!image){return 1;}
    Check(e::StartupCurrent(context.image,context.image+0x1140e9e),"exact bootstrap path accepted");
    Check(!e::StartupCurrent(context.image,context.image+0x1140e9d),"late/arbitrary caller rejected");
    image[0x1140e70]^=1;Check(!e::StartupCurrent(context.image,context.image+0x1140e9e),"changed bootstrap rejected");image[0x1140e70]^=1;
    auto* nt=reinterpret_cast<IMAGE_NT_HEADERS32*>(image+0x80);nt->OptionalHeader.DataDirectory[9].Size=1;
    Check(!e::StartupCurrent(context.image,context.image+0x1140e9e),"nonempty TLS rejects startup qualification");nt->OptionalHeader.DataDirectory[9].Size=0;
    const bool partial=argc==2 && std::strcmp(argv[1],"partial")==0;
    bootstrap_fixture::verified_image=context.image;
    const auto pristine=[&] {
        bool same=!e::attempted && !e::handler && !e::Ready();
        for(const auto& site:e::sites){same=same && !site.owned
            && std::memcmp(image+site.rva,site.bytes.data(),site.bytes.size())==0;}
        for(const auto& slot:e::slots){same=same && !slot.owned
            && e::Word(context.image+slot.rva,static_cast<std::uint32_t>(context.image+slot.original_rva));}
        return same;
    };
    SetLastError(2468);
    Check(!e::StartAtBootstrap(context.image,context.image+0x1140e9e)
        && GetLastError()==2468 && pristine() && bootstrap_fixture::image_checks==0,
        "cold identity rejects public startup before verification or hook mutation");
    bootstrap_fixture::identity_ready=true;
    const char* qualified_digest=bootstrap_fixture::digest;
    for(const char* denied:{"e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
                            "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5",
                            "a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a",
                            "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}){
        bootstrap_fixture::digest=denied;
        Check(!e::StartAtBootstrap(context.image,context.image+0x1140e9e)
            && pristine() && bootstrap_fixture::image_checks==0,
            "original14/original15/original16 and unknown images cannot install native effects hooks");
    }
    bootstrap_fixture::digest=qualified_digest;

    Check(!e::StartAtBootstrap(context.image,context.image+0x1140e9d)
        && GetLastError()==2468 && pristine() && bootstrap_fixture::image_checks==0,
        "initialized identity cannot authorize late caller");
    bootstrap_fixture::image_valid=false;
    Check(!e::StartAtBootstrap(context.image,context.image+0x1140e9e)
        && GetLastError()==2468 && pristine(),"failed image qualification leaves hooks pristine");
    bootstrap_fixture::image_valid=true;
    bootstrap_fixture::verified_image=context.image+4;
    Check(!e::StartAtBootstrap(context.image,context.image+0x1140e9e)
        && GetLastError()==2468 && pristine(),"different verified image leaves hooks pristine");
    bootstrap_fixture::verified_image=context.image;
    const bool started=partial ? e::StartBound(context.image,Partial)
        : e::StartAtBootstrap(context.image,context.image+0x1140e9e);
    Check(started!=partial,"installation result through public bootstrap except fault-injection mode");
    if(!partial){
        Check(GetLastError()==2468 && e::Ready(),"public startup preserves LastError and installs all hooks");
        Check(!e::StartAtBootstrap(context.image,context.image+0x1140e9d) && e::Ready()
            && GetLastError()==2468,"installed observer does not authorize a late caller");
    }
    if(partial){Check(!e::Ready() && e::sites[0].owned && !e::sites[2].owned,"partial install retains ownership without readiness");TestTrap(e::sites[0]);return failures?1:0;}
    e::original_add=reinterpret_cast<e::OneArg>(&OriginalAdd);e::original_remove=reinterpret_cast<e::TwoArgs>(&OriginalRemove);
    e::original_incoming=reinterpret_cast<e::NoArgs>(&OriginalNoArgs);e::original_rebuild=reinterpret_cast<e::NoArgs>(&OriginalNoArgs);
    e::original_equipment=reinterpret_cast<e::OneArg>(&OriginalEquipment);
    e::Snapshot snapshot;Check(e::Capture(context,snapshot)==e::Unknown::none && snapshot.Complete() && snapshot.count==1,"complete copied primary census");
    Check(snapshot.effects[0].descriptor_id==123 && snapshot.effects[0].action_id==456 && snapshot.effects[0].source_words[2]==429021400,"values preserve descriptor/action/source distinction");
    Check(e::Revalidate(context,snapshot),"fresh same owner snapshot revalidates");
    for(std::uint32_t kind:{0U,2U}){
        Put(Address(record)+0x24,kind);Put(Address(record)+0x60,115.0);Put(context.image+0x16a2d70,100.0);
        Check(e::Capture(context,snapshot)==e::Unknown::none&&snapshot.effects[0].remaining_ms==15000
            &&snapshot.effects[0].deadline_stamp==std::bit_cast<std::uint64_t>(115.0),"native timed coverage captures deadline and15s countdown");
        Put(context.image+0x16a2d70,116.0);
        Check(e::Capture(context,snapshot)==e::Unknown::none&&snapshot.count==1&&snapshot.effects[0].remaining_ms==0
            &&snapshot.effects[0].deadline_stamp,"past deadline remains present with due scheduling hint");
    }
    for(double deadline:{0.0,-1000.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN(),1e20}){
        Put(Address(record)+0x60,deadline);
        Check(e::Capture(context,snapshot)==e::Unknown::none&&snapshot.count==1&&!snapshot.effects[0].deadline_stamp
            &&!snapshot.effects[0].remaining_ms,"invalid or unbounded timer preserves coverage without proactive authority");
    }
    Put(Address(record)+0x60,115.0);Put(Address(record)+0x24,std::uint32_t{1});
    Check(e::Capture(context,snapshot)==e::Unknown::none&&!snapshot.effects[0].deadline_stamp,"untimed class remains present without countdown");
    Fill();Check(e::Capture(context,snapshot)==e::Unknown::none,"restore ordinary effect fixture");
    auto substituted=context;substituted.owner=reinterpret_cast<void*>(1);
    Check(!e::Revalidate(substituted,snapshot),"same-key substituted owner rejected");
    substituted=context;substituted.current=OtherCurrent;
    Check(!e::Revalidate(substituted,snapshot),"same-key substituted callback rejected");
    auto replacement_actor=actor;substituted=context;substituted.actor=Address(replacement_actor);
    Put(context.image+0x16a2d98,static_cast<std::uint32_t>(substituted.actor));
    Check(!e::Revalidate(substituted,snapshot),"same-key same-scene replaced actor context rejected");
    Put(context.image+0x16a2d98,static_cast<std::uint32_t>(context.actor));
    const auto first=snapshot.epoch;SetLastError(1234);
    auto add=reinterpret_cast<e::OneArg>(*reinterpret_cast<std::uintptr_t*>(image+0x1141600));
    Check(add(reinterpret_cast<void*>(context.actor+0x588),77)==987 && GetLastError()==5678,"real vtable ABI forwards return and LastError");
    Check(e::Epoch()==first+2 && e::depth==0 && !e::Revalidate(context,snapshot),"mutation invalidates epoch and restores depth");
    Check(e::RemoveHook(reinterpret_cast<void*>(context.actor+0x588),nullptr,7,8)==654,"remove wrapper return");
    Check(e::IncomingHook(reinterpret_cast<void*>(context.actor),nullptr)==321 && e::RebuildHook(reinterpret_cast<void*>(context.actor),nullptr)==321,"whole incoming/rebuild wrappers");
    Check(e::EquipmentHook(reinterpret_cast<void*>(context.actor),nullptr,99)==222 && calls==5,"all original wrappers called exactly once");
    for(const auto& site:e::sites){TestTrap(site);}
    const bool outer=e::EnterMutation(),inner=e::EnterMutation();Check(e::depth==2,"nested mutation depth");
    e::LeaveMutation(inner,false);Check(e::Capture(context,snapshot)==e::Unknown::mutation_active,"outer rebuild blocks even after child returns");e::LeaveMutation(outer,false);
    std::atomic<bool> entered=false,release=false;
    std::thread worker([&]{const bool counted=e::EnterMutation();entered=true;while(!release){SwitchToThread();}e::LeaveMutation(counted,false);});
    while(!entered){SwitchToThread();}Check(e::Capture(context,snapshot)==e::Unknown::mutation_active,"global depth rejects another thread mutation");release=true;worker.join();
    current=false;Check(e::Capture(context,snapshot)==e::Unknown::identity && !snapshot.Complete(),"revoked owner never empty authority");current=true;
    mutate_callback=true;Check(e::Capture(context,snapshot)==e::Unknown::changed,"callback epoch change rejected");mutate_callback=false;
    auto altered=context;altered.actor_key[1]++;Check(e::Capture(altered,snapshot)==e::Unknown::identity,"reused actor pointer wrong key rejected");
    Put(Address(actor)+0x58c,e::Vector{});Check(e::Capture(context,snapshot)==e::Unknown::none && snapshot.count==0,"qualified true empty vector");
    Fill();Put(Address(actor)+0x58c,e::Vector{1,9,17});Check(e::Capture(context,snapshot)==e::Unknown::geometry,"misaligned vector rejects");
    Fill();auto p=static_cast<std::uint32_t>(Address(entries));Put(Address(actor)+0x58c,e::Vector{p,p+8,p+8*257});Check(e::Capture(context,snapshot)==e::Unknown::geometry,"capacity bound rejects");
    Fill();entries[1]=entries[0];Put(Address(actor)+0x58c,e::Vector{p,p+16,p+16});Check(e::Capture(context,snapshot)==e::Unknown::geometry,"duplicate owned record pointer rejects");
    Fill();descriptor[0x4c]=1;Check(e::Capture(context,snapshot)==e::Unknown::none && snapshot.effects[0].local_add_suppression==1,"nonretained descriptor remains explicit metadata never inferred missing");
    Fill();Put(Address(record)+0x24,std::uint32_t{3});Check(e::Capture(context,snapshot)==e::Unknown::unsupported,"unknown record class rejects completeness");
    Fill();Put(Address(action),std::uint32_t{7});Check(e::Capture(context,snapshot)==e::Unknown::unsupported,"unknown action table rejects completeness");
    Fill();entries[0][1]=4;Check(e::Capture(context,snapshot)==e::Unknown::read_fault,"unreadable record rejects without fabricated empty");Fill();
    if(argc==2 && std::strcmp(argv[1],"saturation")==0){InterlockedExchange64(&e::epoch,MAXLONGLONG-1);e::Advance();Check(!e::Ready() && !e::Epoch(),"epoch saturation permanently disables");return failures?1:0;}
    if(argc==2 && std::strcmp(argv[1],"cpp")==0){e::original_add=reinterpret_cast<e::OneArg>(&ThrowCpp);bool caught=false;try{e::AddHook(nullptr,nullptr,0);}catch(const std::runtime_error&){caught=true;}Check(caught && e::depth==0 && !e::Ready(),"C++ unwind preserves exception/restores depth/poisons");}
    else{e::original_add=reinterpret_cast<e::OneArg>(&ThrowSeh);Check(InvokeSeh() && e::depth==0 && !e::Ready(),"SEH unwind preserves exception/restores depth/poisons");}
    return failures?1:0;
}
