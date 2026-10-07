// Synthetic image/stream fixtures test wrapper ABI and failure isolation, not server semantics.
#include "item_application_trace.cpp"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <fstream>
namespace t=wonderbane::extension::item_trace;
namespace w=wonderbane::extension::actor::wire;
namespace m=wonderbane::extension::movement;
namespace {
unsigned checks{},decoded{},processed{},destroyed{},fail_at{},installs{},fault{};
std::uint64_t epoch=7;bool change_scene{},reenter{};void* nested{};
void Check(bool ok,const char* label){++checks;if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}}
void NativeFault(){if(fault==1){throw std::runtime_error("native");}if(fault==2){RaiseException(0xe1234567,0,0,nullptr);}}
void __fastcall DecodeOriginal(void*,void*,void*){++decoded;NativeFault();SetLastError(0x1234);}
std::uint32_t __fastcall ProcessOriginal(void*,void*){
    ++processed;NativeFault();if(change_scene){++epoch;}
    if(reenter){reenter=false;t::ProcessHook<1>(nested,nullptr);}
    SetLastError(0x5678);return 0xdeadbeef;
}
void* __fastcall DestroyOriginal(void* message,void*,unsigned){++destroyed;NativeFault();SetLastError(0x9abc);return message;}
bool SehProcess(void* message){__try{t::ProcessHook<0>(message,nullptr);}__except(GetExceptionCode()==0xe1234567?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH){return true;}return false;}
t::Record Last(){t::Record result{};std::memcpy(&result,&t::storage->records[(t::storage->sequence-1)%t::kCapacity],sizeof(result));return result;}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept{return false;}
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept{return false;}
bool ReadNativeMovementLifetime(NativeScene& out) noexcept{out={};out.epoch=epoch;out.identity={42,53};return true;}
bool NativeMovementLifetimeCurrent(const NativeScene& value) noexcept{return value.epoch && value.epoch==epoch;}
}
DWORD ReplaceImportAddressSlot(std::uint32_t* slot,std::uint32_t expected,std::uint32_t replacement) noexcept{
    const auto prior=InterlockedCompareExchange(reinterpret_cast<LONG*>(slot),static_cast<LONG>(replacement),static_cast<LONG>(expected));
    if(static_cast<std::uint32_t>(prior)!=expected){return ERROR_INVALID_DATA;}
    return ++installs==fail_at?ERROR_ACCESS_DENIED:ERROR_SUCCESS;
}
}
int main(int argc,char** argv){
    fail_at=argc>1?static_cast<unsigned>(std::strtoul(argv[1],nullptr,10)):0;
    auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1200000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));Check(image,"allocate");
    const auto base=reinterpret_cast<std::uintptr_t>(image);
    std::array<std::uint32_t*,6> slots{};
    const std::array<std::uint32_t,6> targets{reinterpret_cast<std::uint32_t>(&DestroyOriginal),reinterpret_cast<std::uint32_t>(&ProcessOriginal),
        reinterpret_cast<std::uint32_t>(&DecodeOriginal),reinterpret_cast<std::uint32_t>(&DestroyOriginal),reinterpret_cast<std::uint32_t>(&ProcessOriginal),reinterpret_cast<std::uint32_t>(&DecodeOriginal)};
    for(unsigned i=0;i<6;++i){slots[i]=reinterpret_cast<std::uint32_t*>(base+t::kTables[i/3]+t::kSlots[i%3]);*slots[i]=targets[i];}
    // Synthetic caller ends at the exact qualified generic-decoder return RVA.
    constexpr unsigned char stub[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,0x8b,0x01,0xff,0x75,0x0c,0xff,0x50,0x1c,0x5d,0xc2,0x08,0x00};
    auto* at=image+t::kDecoderReturn-14;std::memcpy(at,stub,sizeof(stub));DWORD protection{};
    Check(VirtualProtect(at,sizeof(stub),PAGE_EXECUTE_READ,&protection)&&FlushInstructionCache(GetCurrentProcess(),at,sizeof(stub)),"caller executable");
    using Decoder=void(__stdcall*)(void*,void*);const auto decode=reinterpret_cast<Decoder>(at);
    const wonderbane::extension::ProcessIdentity identity{GetCurrentProcessId(),123456789};
    Check(t::StartBound(identity,base,slots,targets)==static_cast<DWORD>(fail_at?ERROR_ACCESS_DENIED:ERROR_SUCCESS),"install");
    if(fail_at){for(unsigned i=0;i<6;++i){Check(*slots[i]==targets[i],"partial installation restores exact owned slots");}
        t::DecodeHook<0>(nullptr,nullptr,nullptr);Check(t::ProcessHook<1>(nullptr,nullptr)==0xdeadbeef,"late original preserved");
        t::DestroyHook<1>(nullptr,nullptr,0);Check(!t::storage&&decoded==1&&processed==1&&destroyed==1,"failed observer cannot disable originals");return 0;}
    std::array<std::uint32_t,44> item{},power{};std::array<std::uint32_t,8> socket{};
    item[0]=static_cast<std::uint32_t>(base+t::kTables[0]);item[28]=2;item[29]=1;item[30]=123;item[31]=30;item[32]=42;item[33]=53;
    power[0]=static_cast<std::uint32_t>(base+t::kTables[1]);for(unsigned i=32;i<43;++i){power[i]=i;}
    socket[0]=static_cast<std::uint32_t>(base+0x116019c);
    decode(item.data(),socket.data());Check(GetLastError()==0x1234,"decode LastError");
    Check(t::ProcessHook<0>(item.data(),nullptr)==0xdeadbeef&&GetLastError()==0x5678,"process return and LastError");
    Check(Last().flags==7&&Last().decode_sequence==1&&Last().payload[2]==123&&Last().native_return==0xdeadbeef,"single-use item decode lineage");
    Check(!w::Any(Last().request)&&!w::Any(Last().command),"incoming has no invented request correlation");
    t::ProcessHook<0>(item.data(),nullptr);Check(!(Last().flags&4),"repeat process has no ticket");
    decode(item.data(),socket.data());t::DestroyHook<0>(item.data(),nullptr,0);Check(GetLastError()==0x9abc,"destructor LastError");
    t::ProcessHook<0>(item.data(),nullptr);Check(!(Last().flags&4),"destruction invalidates reused object");
    decode(item.data(),socket.data());++item[30];t::ProcessHook<0>(item.data(),nullptr);Check(!(Last().flags&4),"changed body loses ticket");
    decode(item.data(),socket.data());++epoch;t::ProcessHook<0>(item.data(),nullptr);Check(!(Last().flags&4),"scene change loses lineage");
    decode(item.data(),socket.data());change_scene=true;t::ProcessHook<0>(item.data(),nullptr);change_scene=false;
    Check(!(Last().flags&6)&&!Last().scene_epoch&&!Last().decode_sequence,"scene change during native call removes scene and lineage");
    item[28]=1;decode(item.data(),socket.data());Check(!Last().payload[4]&&!Last().payload[5],"absent subtype recipient normalized");item[28]=2;
    decode(power.data(),socket.data());t::ProcessHook<1>(power.data(),nullptr);Check(Last().flags==7&&Last().kind==2&&Last().payload[10]==42,"power raw payload");
    decode(item.data(),socket.data());fault=1;bool caught=false;try{decode(item.data(),socket.data());}catch(const std::runtime_error&){caught=true;}fault=0;
    Check(caught,"native decode exception propagates");t::ProcessHook<0>(item.data(),nullptr);Check(!(Last().flags&4),"failed re-decode cannot inherit old ticket");
    fault=2;Check(SehProcess(item.data()),"native SEH propagates");fault=0;
    nested=power.data();reenter=true;t::ProcessHook<0>(item.data(),nullptr);Check(!reenter,"reentrant native call outside recorder lock");
    const auto before=t::storage->sequence;socket[7]=1;decode(item.data(),socket.data());Check(t::storage->sequence==before,"retired socket excluded");socket[7]=0;
    t::ProcessHook<0>(reinterpret_cast<void*>(0x10000),nullptr);Check(!(Last().flags&1),"unreadable copied body is unknown and native still called");
    std::array<std::array<std::uint32_t,44>,65> messages{};for(auto& value:messages){value=item;decode(value.data(),socket.data());}
    Check(t::storage->ticket_drops>0,"bounded ticket eviction reported");
    for(unsigned i=0;i<300;++i){t::ProcessHook<0>(item.data(),nullptr);}
    Check(t::storage->overwritten==t::storage->sequence-static_cast<LONG64>(t::kCapacity),"ring overwrite reported");
    w::Command command{};command.host={1,1,1};command.window=1;
    command.grant.generation=1;command.grant.scene=epoch;command.grant.owner=1;
    command.grant.token.worker[0]='w';command.grant.token.operation[0]='o';
    command.request[0]=1;command.parent_id[0]=2;command.parent_digest[0]=3;
    command.action=w::Action::use_item;command.recipient=w::Recipient::actor;
    command.item_key[0]=5802955;command.item_key[1]=30;command.template_key[0]=980066;
    command.item_hint=0x10000;command.template_hint=0x20000;command.selector_index=0;
    command.manifest_digest[0]=4;command.publication_revision=1;command.snapshot_id[0]=5;
    Check(w::Valid(command),"immutable owned item fixture valid");m::NativeScene scene{};m::ReadNativeMovementLifetime(scene);
    w::Digest digest{};Check(w::HashCommand(command,digest),"owned digest");SetLastError(0x7654);
    t::OwnedReturn(command,scene,w::Outcome::queued,w::Entry::entered,w::LocalSettlement::settled,w::outbound_queued);
    Check(GetLastError()==0x7654&&Last().stage==4&&Last().request==command.request&&Last().command==digest,"exact owned return immutable request without LastError changes");
    Check(!Last().decode_sequence&&!(Last().flags&4)&&Last().payload[2]==5802955,"owned queue result has no invented receive lineage");
    const auto owned_sequence=t::storage->sequence;command.version=0;
    t::OwnedReturn(command,scene,w::Outcome::queued,w::Entry::entered,w::LocalSettlement::settled,w::outbound_queued);
    Check(t::storage->sequence==owned_sequence,"malformed owned command not recorded");
    command.version=3;command.action=w::Action::self_power;command.power_id=429590426;
    command.item_key[0]=command.item_key[1]=command.template_key[0]=command.template_key[1]=0;
    command.item_hint=command.template_hint=0;command.request[0]=6;
    wonderbane::extension::combat::power::Receipt power_result{};
    // The coordinated peace-mode slice appends internal availability value 4.
    power_result.availability=static_cast<wonderbane::extension::combat::power::Availability>(4);
    t::OwnedReturn(command,scene,w::Outcome::deferred,w::Entry::never_entered,w::LocalSettlement::settled,0,&power_result);
    Check(Last().payload[5]==4&&!Last().payload[1],"no-entry mode refusal retains diagnostic availability");
    power_result={};
    power_result.native_entered=true;power_result.result=wonderbane::extension::combat::power::Result::uncertain;
    power_result.observation={true,true,true,true,false,3,2,3,5,0x101};
    Check(w::Valid(command)&&w::HashCommand(command,digest),"immutable owned power fixture valid");
    SetLastError(0xabcd);
    t::OwnedReturn(command,scene,w::Outcome::uncertain,w::Entry::entered,w::LocalSettlement::pending,w::uncertain_history,&power_result);
    Check(GetLastError()==0xabcd&&Last().kind==2&&Last().stage==4&&Last().command==digest
        &&Last().payload[0]==429590426&&Last().payload[1]==49&&Last().payload[6]==3
        &&Last().payload[7]==2&&Last().payload[8]==3&&Last().payload[9]==5&&Last().payload[10]==0x30101,
        "owned power preserves false return, independent metadata and immutable correlation");
    Check(!Last().decode_sequence&&!(Last().flags&4),"owned power has no fabricated incoming lineage");
    wchar_t name[160]{};StringCchPrintfW(name,160,L"Local\\ShadowbaneLab.Extension.ItemApplication.v1.%lu.123456789",GetCurrentProcessId());
    HANDLE reader=OpenFileMappingW(FILE_MAP_READ,FALSE,name);Check(reader!=nullptr,"same-user read mapping");
    HANDLE writer=OpenFileMappingW(FILE_MAP_WRITE,FALSE,name);Check(!writer,"external writer denied");
    auto* view=static_cast<const t::Storage*>(MapViewOfFile(reader,FILE_MAP_READ,0,0,sizeof(t::Storage)));Check(view!=nullptr,"read view");
    if(argc==3&&std::strcmp(argv[1],"snapshot")==0){std::ofstream file(argv[2],std::ios::binary);file.write(reinterpret_cast<const char*>(view),sizeof(t::Storage));Check(file.good(),"export fixture bytes");}
    t::Stop();Check(view->stopped==1,"reader sees explicit stop");UnmapViewOfFile(view);CloseHandle(reader);
    Check(t::ProcessHook<0>(item.data(),nullptr)==0xdeadbeef,"late callback after stop retains original");
    for(unsigned i=0;i<6;++i){Check(*slots[i]==targets[i],"stop restores own slots");}
    VirtualFree(image,0,MEM_RELEASE);std::printf("item trace: %u checks passed\n",checks);return 0;
}
