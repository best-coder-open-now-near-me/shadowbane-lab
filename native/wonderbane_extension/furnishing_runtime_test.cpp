// Production runtime, ownership transaction and receipts; only operating-system
// input/GL and native engine calls are controlled. No client binary is executed.
#include "furnishing_test_fixture.h"
#include "furnishing_native_calls.h"
#include "furnishing_resources.h"
#include "movement_native_ui.h"
#include <gl/GL.h>
#include <string>
#include <cstring>
#include <thread>
namespace {
Fixture fixture;
constexpr A fixture_image=0x400000, native_root=fixture_queue-0xfc, hud=0x310000, actor=0x300000, structure=0x320000;
HWND client=nullptr;
DWORD owner_thread=0;
bool sealed=true,foreground=true,modal=false;
unsigned installed=0,fail_install=0;
A pushed=0,popped=0;
unsigned push_calls=0,pop_calls=0;
f::NativeCalls::FloorResult floor_result=f::NativeCalls::FloorResult::hit;
f::Transform composed{};
void APIENTRY OriginalPush() { ++push_calls; }
void APIENTRY OriginalPop() { ++pop_calls; }
FARPROC WINAPI Procedure(HMODULE,LPCSTR name) {
    return std::strcmp(name,"glPushMatrix")==0?reinterpret_cast<FARPROC>(&OriginalPush):reinterpret_cast<FARPROC>(&OriginalPop);
}
HWND WINAPI Foreground() { return foreground?client:nullptr; }
BOOL WINAPI Cursor(LPPOINT point) { *point={100,100}; return TRUE; }
BOOL WINAPI ToClient(HWND,LPPOINT) { return TRUE; }
void APIENTRY Integer(GLenum name,GLint* value) { *value=name==GL_MATRIX_MODE?GL_MODELVIEW:0; }
}
#define GetProcAddress Procedure
#define GetForegroundWindow Foreground
#define GetCursorPos Cursor
#define ScreenToClient ToClient
#define glGetIntegerv Integer
#include "furnishing_runtime.cpp"
#undef GetProcAddress
#undef GetForegroundWindow
#undef GetCursorPos
#undef ScreenToClient
#undef glGetIntegerv
namespace wonderbane::extension {
std::uint32_t* FindImportAddressSlot(std::uint8_t*,std::size_t,const char*,const char* name) noexcept {
    return std::strcmp(name,"glPushMatrix")==0?&pushed:&popped;
}
DWORD ReplaceImportAddressSlot(std::uint32_t* slot,std::uint32_t expected,std::uint32_t replacement) noexcept {
    assert(*slot==expected); if(++installed==fail_install) { return ERROR_ACCESS_DENIED; } *slot=replacement; return ERROR_SUCCESS;
}
DWORD StartSceneContextObservation(std::uint8_t*,std::size_t) noexcept { return ERROR_SUCCESS; }
namespace movement {
bool ReadNativeMovementLifetime(NativeScene& s) noexcept {
    s={actor,structure,0, native_root,{17,18},7}; return fixture.current;
}
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return fixture.current && s.epoch==7 && GetCurrentThreadId()==owner_thread; }
bool NativeUi::Bind(HWND) noexcept { return true; }
bool NativeUi::Snapshot(POINT client_point,NativeUiState& s) noexcept {
    s={}; s.available=true; s.global_owned=s.keyboard_owned=modal; s.pointer_owned=true;
    s.native_window=native_root; s.native_point=client_point; s.pointer_hud=hud; return true;
}
NativePointResult NativeClientPoint(std::uintptr_t,std::uintptr_t,HWND,POINT p,POINT& out) noexcept {
    out=p; return NativePointResult::valid;
}
}
namespace furnishing {
bool NativeCalls::Configure() noexcept { base_=fixture_image; return sealed; }
bool NativeCalls::Bind(HWND w) noexcept { window_=w; thread_=owner_thread; return Owner(); }
bool NativeCalls::Owner() const noexcept { return fixture.owned && window_ && GetCurrentThreadId()==owner_thread; }
bool NativeCalls::Read(Address at,void* out,std::size_t size) noexcept {
    if(size==4 && (at==reinterpret_cast<A>(&pushed)||at==reinterpret_cast<A>(&popped))) { std::memcpy(out,reinterpret_cast<void*>(at),4); return true; }
    return Fixture::Read(&fixture,at,out,size);
}
bool NativeCalls::RetainModel(Address v,Address* slot) noexcept { return Fixture::Retain(&fixture,v,slot); }
bool NativeCalls::Clone(Address v,Address* slot) noexcept { return Fixture::Clone(&fixture,v,slot); }
bool NativeCalls::Release(Address* slot) noexcept { return Fixture::Release(&fixture,slot); }
bool NativeCalls::Compose(Address v,const Transform& t) noexcept {
    assert(v==fixture_copy && fixture.nodes.empty()); ++fixture.compose_calls; composed=t; return fixture.Enter()&&fixture.Finish();
}
bool NativeCalls::Enqueue(Address v,Address q) noexcept { return Fixture::Enqueue(&fixture,v,q); }
bool NativeCalls::Pool(QueueReceipt::Pool& p) const noexcept { return Fixture::Pool(&fixture,p); }
bool NativeCalls::Erase(Address q,Address n) noexcept { return Fixture::Erase(&fixture,q,n); }
NativeCalls::FloorResult NativeCalls::Floor(const Selection&,int x,int y,std::array<float,3>& out) noexcept {
    assert(x==100 && y==100); out={1,2,3}; return floor_result;
}
bool RenderResources::Source(const Selection& s) noexcept { return Fixture::Source(&fixture,s); }
bool RenderResources::Private(const Selection& s,Address c,Address* out,std::size_t cap,std::size_t* count) noexcept {
    return Fixture::Private(&fixture,s,c,out,cap,count);
}
bool RenderResources::Wrapper(Address,Address) noexcept { return fixture.wrapper_valid; }
}
}
namespace {
void Words(A at,std::initializer_list<A> values) { for(A v:values) { fixture.Put(at,v); at+=4; } }
void Type(A at,A rva) { fixture.Put(at,fixture_image+rva); }
void Setup() {
    fixture.Tree(); fixture.Put(fixture_image+0x16a9dd4,A{0});
    IMAGE_DOS_HEADER dos{}; dos.e_lfanew=0x80; fixture.Put(fixture_image,dos);
    IMAGE_NT_HEADERS32 nt{}; nt.OptionalHeader.SizeOfImage=0x1700000; fixture.Put(fixture_image+0x80,nt);
    constexpr A manager=0x330000,list=0x340000,layout=0x350000,row=0x360000,entry=0x370000,deed=0x380000;
    constexpr A root_head=0x390000,link=0x391000,component=0x392000,actor_pose=0x393000;
    constexpr A building_component=0x394000,building_pose=0x395000,children=0x396000,rows=0x397000,name=0x398000,floors=0x399000;
    fixture.Put(fixture_image+0x16a7bfc,native_root); fixture.Put(fixture_image+0x16a2d98,actor);
    Type(native_root,0x1174884); fixture.Put(native_root+0x64,A{2}); fixture.Put(native_root+0x20,root_head); fixture.Put(native_root+0xa4,manager);
    Words(root_head,{link,link}); Words(link,{root_head,root_head,hud}); Type(hud,0x1167c68);
    Type(hud+4,0x1167c2c); Type(fixture_image+0x1167c2c+0x1c,0x25167);
    Type(fixture_image+0x1167c68+0x14c,0x9e0d); Type(fixture_image+0x1167c68+0x154,0x140ba); Type(fixture_image+0x1167c68+0x244,0x22a39);
    Words(hud+8,{0,0,600,600}); fixture.Put(hud+0x640,6.25f); fixture.Put(hud+0x2a0,A{1});
    Type(actor,0x114165c); fixture.Put(actor+0x4b0,component); fixture.Put(component,actor_pose); fixture.Put(actor_pose+8,structure);
    Type(structure,0x1177c0c); Words(structure+0x18,{4761372,8});
    fixture.Put(structure+0x4b0,building_component); fixture.Put(building_component,building_pose);
    fixture.Put(building_pose+0x20,f::Transform{0,0,0,1,0,0,0,1,1,1}); Words(structure+0x734,{floors,floors+12});
    Type(manager,0x1171adc); fixture.Put(manager+0xa8,hud); fixture.Put(hud+0x104,manager); fixture.Put(hud+0x64c,structure);
    fixture.Put(hud+0x524,list); fixture.Put(hud+0x648,layout); fixture.Put(hud+0x660,entry);
    Words(hud+0x54,{children,children+8,children+8}); Words(children,{list,layout});
    Type(list,0x116acf0); fixture.Put(list+0x3bc,hud); fixture.Put(layout+0x3bc,hud);
    Words(layout+0x168,{name,name+26,name+28}); const char16_t label[]=u"BTNPROPLAYOUT"; fixture.Put(name,label);
    Words(list+0x408,{rows,rows+4,rows+4}); fixture.Put(rows,row); fixture.Put(list+0x404,row);
    Type(row,0x116aebc); fixture.Put(row+0x3bc,hud); fixture.Put(row+0x458,list); fixture.Put(row+0x44c,entry);
    Type(entry,0x1169908); fixture.Put(entry+8,A{0x25}); Words(entry+0x10,{5017277,30});
    fixture.Put(entry+0x20,deed); fixture.Put(entry+0x24,fixture_model); Type(deed,0x1142468); Words(deed+0x7b8,{622657,0});
    Type(fixture_model,0x1143540); Type(fixture_model+0x44,0x114350c); fixture.Put(fixture_model+0xc0,fixture_source);
    Type(fixture_source,0x1149dbc); Type(fixture_source+0x30,0x1149d94);
    fixture.Put(hud+0x628,A{2}); Words(hud+0x630,{400,400}); fixture.Put(hud+0x638,std::array<float,2>{64,54}); fixture.Put(hud+0x37c,1.0f);
}
}
int main(int argc,char** argv) {
    using namespace wonderbane::extension; using namespace furnishing;
    assert(argc==2); const std::string mode=argv[1]; owner_thread=GetCurrentThreadId(); Setup();
    pushed=reinterpret_cast<A>(&OriginalPush); popped=reinterpret_cast<A>(&OriginalPop);
    client=CreateWindowW(L"STATIC",L"preview runtime fixture",WS_OVERLAPPEDWINDOW,0,0,1000,800,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr); assert(client);
    if(mode=="install1") { fail_install=1; } if(mode=="install2") { fail_install=2; } if(mode=="unsealed") { sealed=false; }
    Renderer(true);
    const bool started=Start();
    if(fail_install || !sealed) {
        assert(!started && !furnishing_owner_service.load() && !fixture.retain_calls);
        if(fail_install==2) { reinterpret_cast<MatrixCall>(pushed)(); assert(push_calls==1); }
        DestroyWindow(client); return 0;
    }
    assert(started && !Start()); auto* s=runtime.load(); fixture.renderer=&*s->render;
    RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client); assert(s->selected.hud==hud && !s->active);
    Runtime::Action(s,PreviewControls::Action::start);
    RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client);
    assert(s->active && s->posed && composed==fixture_pose && fixture.model_refs==1 && fixture.clone_refs==1);
    if(mode=="rotate") {
        Runtime::Action(s,PreviewControls::Action::hold); Runtime::Action(s,PreviewControls::Action::right);
        RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client); assert(s->held && composed[5]<-0.7f);
    }
    if(mode=="foreign") {
        std::thread other([&] { s->Clear(true); s->Push(); s->Pop(); ContextLost(); OwnerRetire(client); }); other.join();
        assert(!s->terminal && !fixture.enqueue_calls && fixture.releases.empty());
    }
    else if(mode=="alternate") { s->Clear(false); s->Push(); s->Pop(); assert(!fixture.enqueue_calls); }
    else if(mode=="binding") { popped=0; s->Clear(true); s->Push(); s->Pop(); assert(!fixture.enqueue_calls && !s->active); }
    else if(mode=="hidden") { fixture.Put(hud+0x2a0,A{0}); s->Clear(true); s->Push(); s->Pop(); assert(!fixture.enqueue_calls && !s->active); }
    else if(mode=="scene") { fixture.current=false; RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client); assert(!s->active && !fixture.model_refs); }
    else if(mode=="modal") { modal=true; RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client); assert(!s->active && !fixture.model_refs); }
    else if(mode=="no_floor") { floor_result=NativeCalls::FloorResult::miss; RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client); s->Clear(true); s->Push(); s->Pop(); assert(!s->posed && !fixture.enqueue_calls); }
    else {
        s->Clear(true); s->Push(); assert(fixture.enqueue_calls==1 && fixture.nodes.size()==2);
        if(mode=="stop") { Renderer(false); }
        if(mode=="context" || mode=="missed" || mode=="shader") {
            if(mode=="context") { ContextLost(); }
            if(mode=="missed") { s->Clear(true); }
            if(mode=="shader") { fixture.Put(fixture_image+0x16a9dd4,A{1}); s->Pop(); }
            assert(s->terminal && s->render->CurrentState()==R::State::quarantined && fixture.releases.empty());
            const auto clones=fixture.clone_calls; Renderer(true); RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client);
            assert(fixture.clone_calls==clones); DestroyWindow(client); return 0;
        }
        s->Push(); s->Pop(); assert(fixture.nodes.size()==2); // nested drain cannot retire outer
        s->Pop(); assert(fixture.nodes.empty() && fixture.erase_calls==2);
        if(mode=="stop") { assert(!fixture.model_refs && !fixture.clone_refs); }
    }
    Runtime::Action(s,PreviewControls::Action::cancel); RunNativeOwnerServices(reinterpret_cast<void*>(native_root),client);
    assert(fixture.nodes.empty() && !fixture.model_refs && !fixture.clone_refs);
    RetireNativeOwnerServices(client); assert(s->terminal); DestroyWindow(client);
}
