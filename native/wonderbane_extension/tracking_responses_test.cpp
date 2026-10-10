#include "tracking_responses.cpp"
#include "tracking_presentation.cpp"
#include <atomic>
#include <iostream>
#include <fstream>
#include <memory>
#include <thread>
namespace tr = wonderbane::extension::tracking;
namespace {
std::atomic<std::uint64_t> epoch{7};
unsigned decoded=0, processed=0, destroyed=0, fail_at=0, installs=0;
bool replace_scene=false, throw_process=false;
DWORD expected_entry_error=0;
void (*process_presentation)() = nullptr;
void* nested_message=nullptr;
int failures=0;
void Check(bool value,const char* what){if(!value){++failures;std::cerr<<what<<'\n';}}
void __fastcall DecodeOriginal(void*,void*,void*){++decoded;SetLastError(0x5678);}
std::uint32_t __fastcall ProcessOriginal(void*,void*){
    if(expected_entry_error){Check(GetLastError()==expected_entry_error,"native Process receives original LastError");expected_entry_error=0;}
    ++processed;if(process_presentation){process_presentation();}if(replace_scene){++epoch;}
    if(nested_message){auto* next=nested_message;nested_message=nullptr;tr::ProcessHook(next,nullptr);}
    if(throw_process){SetLastError(0x9876);RaiseException(0xe0420201,0,0,nullptr);}
    SetLastError(0x8765);return 0x12345678;
}
void* __fastcall DestroyOriginal(void* p,void*,unsigned){++destroyed;return p;}
bool Fault(void* message){
    __try{tr::ProcessHook(message,nullptr);return false;}
    __except(EXCEPTION_EXECUTE_HANDLER){return true;}
}
const tr::Record& Last(){return tr::storage->records[(tr::storage->sequence-1)%tr::kCapacity];}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept{return false;}
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept{return false;}
bool ReadNativeMovementLifetime(NativeScene& s) noexcept{s={};s.epoch=epoch;s.identity={42,53};return s.epoch!=0;}
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept{return s.epoch&&s.epoch==epoch;}
}
DWORD ReplaceImportAddressSlot(std::uint32_t* slot,std::uint32_t expected,std::uint32_t value) noexcept{
    auto before=InterlockedCompareExchange(reinterpret_cast<LONG*>(slot),static_cast<LONG>(value),static_cast<LONG>(expected));
    if(static_cast<std::uint32_t>(before)!=expected){return ERROR_INVALID_DATA;}
    return ++installs==fail_at?ERROR_ACCESS_DENIED:ERROR_SUCCESS;
}
}
namespace presentation_tests {
namespace pp = tr::presentation;
using wonderbane::extension::movement::NativeScene;
pp::Hud hud{};
unsigned closes=0, captures=0;
bool readable=true, close_ok=true;
NativeScene Scene(){NativeScene s{};s.epoch=epoch;s.identity={42,53};return s;}
bool Capture(const NativeScene& scene,pp::Hud& out) noexcept {
    ++captures;out=hud;return readable&&scene.epoch==epoch;
}
bool Close(const NativeScene&,const pp::Hud& expected) noexcept {
    if(!close_ok||expected.address!=hud.address){return false;}
    ++closes;hud={};return true;
}
void Replaced(){hud={0x22000,429578587};}
unsigned native_closes=0;
void __fastcall NativeClose(void* object,void*,bool close) {
    Check(close,"native close bool matches ordinary handler");
    ++native_closes;static_cast<unsigned char*>(object)[0x271]=1;
}
void Boundary(std::uintptr_t image){
    // Real production memory walk and native ABI call, backed by test-owned HUD
    // nodes. Only the native lifecycle body is substituted; no production bypass.
    alignas(4) std::array<std::uint32_t,32> root{};
    alignas(4) std::array<std::uint32_t,256> object{};
    alignas(4) std::array<std::uint32_t,3> head{},node{};
    auto ptr=[](auto* value){return reinterpret_cast<std::uint32_t>(value);};
    root[0]=static_cast<std::uint32_t>(image+pp::kRootTable);root[0x64/4]=2;root[0x20/4]=ptr(head.data());
    head[0]=head[1]=ptr(node.data());node[0]=node[1]=ptr(head.data());node[2]=ptr(object.data());
    object[0]=static_cast<std::uint32_t>(image+pp::kHudTable);object[0xdc/4]=0x34;object[0x3b8/4]=429578587;
    *reinterpret_cast<std::uint32_t*>(image+pp::kRoot)=ptr(root.data());
    auto* slot=reinterpret_cast<std::uint32_t*>(image+pp::kHudTable+0x10c);*slot=static_cast<std::uint32_t>(image+pp::kClose);
    auto* code=reinterpret_cast<unsigned char*>(image+pp::kClose);
    constexpr unsigned char thunk[]{0x55,0x8b,0xec,0x81,0xec,0x04,0x02,0x00,0x00,0x81,0xc4,0x04,0x02,0x00,0x00,0x5d,0xe9,0,0,0,0};
    std::memcpy(code,thunk,sizeof(thunk));
    const auto displacement=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&NativeClose)-(image+pp::kClose+sizeof(thunk)));
    std::memcpy(code+17,&displacement,4);DWORD previous{};
    Check(VirtualProtect(code,sizeof(thunk),PAGE_EXECUTE_READ,&previous)&&FlushInstructionCache(GetCurrentProcess(),code,sizeof(thunk)),"test native close thunk executable");
    Check(pp::Bind(image),"exact native close prologue/slot bound");
    auto scene=Scene();scene.window=ptr(root.data());pp::Hud observed{};
    Check(pp::Capture(scene,observed)&&observed.address==ptr(object.data()),"bounded native HUD owner walk");
    Check(pp::Close(scene,observed)&&native_closes==1,"production close calls native bool ABI");
    Check(pp::Capture(scene,observed)&&!observed.address,"closed native HUD excluded by native closed flag");
    reinterpret_cast<unsigned char*>(object.data())[0x271]=0;
    Check(pp::Capture(scene,observed),"native HUD reopened");
    --*slot;Check(!pp::Close(scene,observed)&&native_closes==1&&!pp::Bind(image),"changed native close slot rejected");++*slot;
    node[1]=0;Check(!pp::Capture(scene,observed),"broken HUD owner links rejected");node[1]=ptr(head.data());
    root[0x64/4]=1;Check(!pp::Capture(scene,observed),"world transition never closes a HUD");
    pp::Unbind();
}
void Run(void* message,void* socket,void(__stdcall* decode)(void*,void*),std::uintptr_t image){
    Boundary(image);
    pp::capture=Capture;pp::close_hud=Close;pp::base=image;pp::state={};
    pp::Owner owner{};owner[0]=1;auto scene=Scene();
    hud={0x21000,429578587};pp::Arm(scene,owner);
    Check(closes==1&&!hud.address,"automatic policy closes already stuck panel with native lifecycle");
    const auto captured=captures;pp::Owner other{};other[0]=2;pp::Maintain(scene,other);
    Check(captures==captured,"unowned maintenance performs no HUD scan");
    process_presentation=Replaced;decode(message,socket);tr::ProcessHook(message,nullptr);
    Check(closes==2&&!hud.address&&Last().flags==7&&Last().payload.row_count==1,
        "automatic result closes replacement and preserves copied complete contacts");
    pp::ManualQuery();pp::Maintain(scene,owner);pp::Maintain(scene,owner);
    Check(pp::state.manual&&pp::state.manual_pending,"manual intent waits for response while no HUD exists");
    decode(message,socket);tr::ProcessHook(message,nullptr);
    Check(closes==2&&hud.address&&pp::state.manual&&!pp::state.manual_pending,"manual response remains visible");
    // Mimic the native handler's internal close; a reentrant owner tick must not
    // interpret its intermediate absence as a user dismissal.
    auto processing=pp::Begin(scene);hud={};pp::Maintain(scene,owner);Replaced();pp::End(scene,processing,true);
    Check(closes==2&&hud.address&&pp::state.manual,"internal close/replacement preserves manual reservation");
    decode(message,socket);tr::ProcessHook(message,nullptr);
    Check(closes==2&&hud.address,"subsequent automatic responses preserve manual window");
    pp::Retire(owner);pp::Arm(scene,other);
    Check(closes==2&&pp::state.manual,"owner retirement/reentry does not steal manual presentation");
    hud={};pp::Maintain(scene,other);
    Check(!pp::state.manual,"observed native dismissal outside Process releases manual reservation");
    decode(message,socket);tr::ProcessHook(message,nullptr);
    Check(closes==3&&!hud.address,"automatic presentation resumes after actual dismissal");
    pp::Retire(other);hud={0x23000,429578587};pp::Arm(scene,owner);
    Check(pp::state.manual&&closes==3,"owner reentry cannot repeat initial adoption and steal an externally reopened HUD");
    pp::Retire(owner);pp::Arm(scene,other);
    hud={};pp::Maintain(scene,other);
    hud={0x23000,429578587};pp::Maintain(scene,other);
    Check(pp::state.manual&&closes==3,"externally reopened HUD is user presentation without a query");
    hud={};pp::Maintain(scene,other);
    processing=pp::Begin(scene);pp::ManualQuery();Replaced();pp::End(scene,processing,true);
    Check(closes==3&&hud.address,"manual intervention during Process invalidates automatic close token");
    // A pending manual query with an already open window must not be mistaken
    // for dismissal if that old window closes before the response arrives.
    pp::ManualQuery();pp::Maintain(scene,other);hud={};pp::Maintain(scene,other);
    Check(pp::state.manual&&pp::state.manual_pending,"old HUD dismissal does not clear pending manual query");
    processing=pp::Begin(scene);Replaced();pp::End(scene,processing,false,false);hud={};pp::Maintain(scene,other);
    Check(pp::state.manual&&pp::state.manual_pending,"faulting Process cannot resolve pending manual intent");
    pp::Retire(other);processing=pp::Begin(scene);Replaced();pp::End(scene,processing,true);
    Check(closes==3,"retired owner cannot close response");
    ++epoch;scene=Scene();hud={0x24000,429578587};pp::Arm(scene,owner);
    Check(closes==4&&!pp::state.manual,"new scene cannot inherit old manual or automatic ownership");
    processing=pp::Begin(scene);auto nested=pp::Begin(scene);Replaced();pp::End(scene,nested,true);
    Check(closes==4,"nested response does not close while outer native handler still owns UI");
    pp::End(scene,processing,true);Check(closes==5,"outer return safely closes final replacement");
    hud={0x25000,429742427};pp::Arm(scene,owner);
    processing=pp::Begin(scene);pp::End(scene,processing,true);
    Check(closes==5,"Hunt Prey selector never closed as automatic Hunt Foe");
    hud={};pp::Maintain(scene,owner);processing=pp::Begin(scene);Replaced();++epoch;pp::End(scene,processing,true);
    Check(closes==5,"scene loss prevents close");
    scene=Scene();hud={};pp::Arm(scene,owner);readable=false;pp::Maintain(scene,owner);readable=true;Replaced();
    processing=pp::Begin(scene);pp::End(scene,processing,true);
    Check(closes==5,"failed observation retires automatic policy without UI mutation");
    hud={};pp::Arm(scene,owner);close_ok=false;processing=pp::Begin(scene);Replaced();pp::End(scene,processing,true);
    Check(!pp::state.active&&closes==5,"native close failure withdraws automatic presentation ownership");
    close_ok=true;process_presentation=nullptr;pp::Unbind();pp::capture=pp::Capture;pp::close_hud=pp::Close;
}
}
int main(int argc,char** argv){
    if(argc>1){fail_at=static_cast<unsigned>(std::strtoul(argv[1],nullptr,10));}
    auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1700000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!image){return 2;}const auto base=reinterpret_cast<std::uintptr_t>(image);
    std::array<std::uint32_t*,3> slots{};
    std::array<std::uint32_t,3> targets{reinterpret_cast<std::uint32_t>(&DestroyOriginal),reinterpret_cast<std::uint32_t>(&ProcessOriginal),reinterpret_cast<std::uint32_t>(&DecodeOriginal)};
    for(std::size_t i=0;i<3;++i){slots[i]=reinterpret_cast<std::uint32_t*>(image+tr::kTable+tr::kSlots[i]);*slots[i]=targets[i];}
    constexpr unsigned char code[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,0x8b,0x01,0xff,0x75,0x0c,0xff,0x50,0x1c,0x5d,0xc2,0x08,0x00};
    auto* thunk=image+tr::kDecoderReturn-14;std::memcpy(thunk,code,sizeof(code));DWORD protection=0;
    if(!VirtualProtect(thunk,sizeof(code),PAGE_EXECUTE_READ,&protection)||!FlushInstructionCache(GetCurrentProcess(),thunk,sizeof(code))){return 3;}
    using Decoder=void(__stdcall*)(void*,void*);auto decode=reinterpret_cast<Decoder>(thunk);
    const wonderbane::extension::ProcessIdentity identity{GetCurrentProcessId(),123456789};
    Check(tr::StartBound(identity,base,slots,targets)==static_cast<DWORD>(fail_at?ERROR_ACCESS_DENIED:ERROR_SUCCESS),"start");
    if(fail_at){
        for(std::size_t i=0;i<3;++i){Check(*slots[i]==targets[i],"partial install restored");}
        Check(!tr::storage,"failed start has no view");
        Check(tr::ProcessHook(nullptr,nullptr)==0x12345678,"failed-start late call-through");
        tr::Stop();VirtualFree(image,0,MEM_RELEASE);return failures;
    }
    std::array<std::uint32_t,28> message{};std::array<std::uint32_t,8> socket{};
    std::array<std::uint32_t,32> rows{};alignas(4) std::array<std::uint16_t,4> name{u'T',u'e',u's',u't'};
    auto ptr=[](const void* p){return reinterpret_cast<std::uint32_t>(p);};
    message[0]=static_cast<std::uint32_t>(base+tr::kTable);message[24]=429578587;
    message[25]=ptr(rows.data());message[26]=message[25]+64;message[27]=message[25]+128;
    rows[0]=42;rows[1]=53;rows[3]=ptr(name.data());rows[4]=rows[3]+8;rows[5]=rows[4];rows[15]=1;
    socket[0]=static_cast<std::uint32_t>(base+0x116019c);
    tr::Cursor before{};Check(tr::ReadCursor(before),"initial cursor");
    decode(message.data(),socket.data());Check(GetLastError()==0x5678,"decoder LastError");
    expected_entry_error=0x5678;
    Check(tr::ProcessHook(message.data(),nullptr)==0x12345678&&GetLastError()==0x8765,"process call-through");
    Check(decoded==1&&processed==1&&tr::storage->sequence==3,"three stages exactly once");
    Check(Last().flags==7&&Last().processing_generation==2&&Last().decode_sequence==1,"qualified generation");
    Check(Last().payload.rows[0].object==tr::Key{42,53}&&Last().payload.rows[0].name_units==4,"copied identity/name");
    if(argc==3&&std::strcmp(argv[1],"dump")==0){
        std::ofstream output(argv[2],std::ios::binary);
        output.write(reinterpret_cast<const char*>(tr::storage),sizeof(tr::Storage));
        Check(static_cast<bool>(output),"actual native frame exported");
    }
    auto batch=std::make_unique<tr::Batch>();Check(tr::ReadAfter(before,*batch)&&batch->count==3,"contiguous copy");
    name[0]=u'X';Check(Last().payload.rows[0].name[0]==u'T',"no native pointer alias");name[0]=u'T';
    decode(message.data(),socket.data());tr::ProcessHook(message.data(),nullptr);
    Check(Last().processing_generation==5,"identical response distinct processing generation");
    message[26]=message[25];decode(message.data(),socket.data());tr::ProcessHook(message.data(),nullptr);
    Check(Last().flags==7&&Last().payload.row_count==0&&Last().processing_generation==8,"empty response remains complete");
    message[26]=message[25]+64;
    auto nested=message;tr::Cursor nesting{};Check(tr::ReadCursor(nesting),"nesting cursor");
    decode(message.data(),socket.data());decode(nested.data(),socket.data());
    nested_message=nested.data();tr::ProcessHook(message.data(),nullptr);
    Check(tr::ReadAfter(nesting,*batch)&&batch->count==6,"nested stages retained");
    Check(batch->records[4].stage==3&&batch->records[5].stage==3
        &&batch->records[4].flags==7&&batch->records[5].flags==7
        &&batch->records[4].processing_generation>batch->records[5].processing_generation,
        "nested return ordering does not relabel processing generation");
    decode(message.data(),socket.data());++epoch;tr::ProcessHook(message.data(),nullptr);
    Check(Last().flags==3&&Last().decode_sequence==0,"decode from old scene cannot correlate");
    decode(message.data(),socket.data());replace_scene=true;tr::ProcessHook(message.data(),nullptr);replace_scene=false;
    Check(Last().flags==1&&!Last().scene_epoch&&!Last().decode_sequence,"return crossing scene unqualified");
    decode(message.data(),socket.data());tr::DestroyHook(message.data(),nullptr,0);tr::ProcessHook(message.data(),nullptr);
    Check(!(Last().flags&4)&&destroyed==1,"destructor invalidates lineage");
    decode(message.data(),socket.data());name[0]=u'X';tr::ProcessHook(message.data(),nullptr);name[0]=u'T';
    Check(!(Last().flags&4),"changed message not old response");
    auto payload=std::make_unique<tr::Payload>();
    rows[0]=rows[1]=0;Check(!tr::Snapshot(message.data(),*payload),"null contact rejected");rows[0]=42;rows[1]=53;
    rows[4]=rows[3]+194;rows[5]=rows[4];Check(!tr::Snapshot(message.data(),*payload),"long name rejected not truncated");rows[4]=rows[3]+8;rows[5]=rows[4];
    name[0]=0xd800;Check(!tr::Snapshot(message.data(),*payload),"invalid UTF16 rejected");name[0]=u'T';
    std::memcpy(rows.data()+16,rows.data(),64);message[26]+=64;Check(!tr::Snapshot(message.data(),*payload),"duplicate keys rejected");message[26]-=64;
    message[26]++;Check(!tr::Snapshot(message.data(),*payload),"partial row rejected");message[26]--;
    const auto prior=tr::storage->sequence;socket[7]=1;decode(message.data(),socket.data());socket[7]=0;
    Check(tr::storage->sequence==prior,"inactive socket ignored");
    decode(message.data(),socket.data());throw_process=true;Check(Fault(message.data())&&GetLastError()==0x9876,"native exception and LastError propagated");throw_process=false;
    Check(Last().stage==2,"exception has no returned proof");
    Check(!tr::ReadAfter(before,*batch),"ring overrun not hidden");
    presentation_tests::Run(message.data(),socket.data(),decode,base);
    decode(message.data(),socket.data());throw_process=true;Check(Fault(message.data()),"exception after presentation retires bracket");throw_process=false;
    auto* view=static_cast<const tr::Storage*>(MapViewOfFile(tr::mapping,FILE_MAP_READ,0,0,sizeof(tr::Storage)));
    Check(view&&view->records[(view->sequence-1)%tr::kCapacity].stage==2,"read-only mapping actual ABI");
    tr::Stop();Check(view&&view->stopped,"reader sees stop");
    Check(!tr::ReadCursor(before),"stopped cursor invalid");
    Check(tr::StartBound(identity,base,slots,targets)==ERROR_ALREADY_INITIALIZED,"no restart alias");
    for(std::size_t i=0;i<3;++i){Check(*slots[i]==targets[i],"original slots restored");}
    if(view){UnmapViewOfFile(view);}VirtualFree(image,0,MEM_RELEASE);return failures;
}
