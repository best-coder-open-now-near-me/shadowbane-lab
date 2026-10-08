#include "weapon_appearance.h"
#include "moonfire.h"
#include "effects.h"
#include "cel_shading.h"
#include <gl/GL.h>
#include <strsafe.h>
#include <array>
#include <cmath>
#include <cstring>
namespace wonderbane::extension::weapon {
namespace {
constexpr std::uint32_t magic=0x4B574257U;
#pragma pack(push,4)
struct Control {
    std::uint32_t tag=magic,version=2,size=96,pid=0;
    std::uint64_t creation=0;
    volatile LONG desired=0,applied=0,error=0;
    float length=.8F;
    volatile LONG matches=0,draws=0;
    FireSettings fire{};
    volatile LONG fire_draws=0,fire_reason=0;
    std::uint32_t reserved[3]{};
};
#pragma pack(pop)
static_assert(sizeof(Control)==96);
HANDLE mapping=nullptr;
Control* control=nullptr;
std::uint32_t image_base=0;
std::uint64_t creation=0;
thread_local std::array<std::uint32_t,2> weapons{};
thread_local effects::Attachment owner{};
thread_local unsigned count=0;
thread_local int scoped_index=-1;
thread_local FireSettings fire{};
thread_local std::array<bool,2> decorated{};
thread_local double seconds=0;
thread_local float length=1.F,scoped=1.F;
thread_local bool active=false,scaled=false;
thread_local HGLRC context=nullptr;
bool Read(void*,std::uint32_t address,void* result,std::size_t bytes) {
    if(address<0x10000 || address>0x7FFEFFFF || bytes>0x7FFEFFFF-address)return false;
    SIZE_T copied=0;
    return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),result,bytes,&copied) && copied==bytes;
}
bool Word(std::uint32_t address,std::uint32_t& value) {return Read(nullptr,address,&value,4);}
bool Collect() {
    owner=effects::Resolve(Read,nullptr,image_base,0);
    std::array<std::uint32_t,128> tree{};
    if(!owner.valid || !Word(owner.actor+0xc0,tree[0]) || !tree[0])return false;
    unsigned nodes=1;
    for(unsigned n=0;n<nodes;++n){
        std::uint32_t table=0,id=0,begin=0,end=0;
        const auto r=tree[n];
        if(!Word(r,table) || table!=image_base+0x1149dbc || !Word(r+0x10,id)
            || !Word(r+0x3c,begin) || !Word(r+0x40,end) || end<begin
            || (end-begin)%4 || end-begin>128*4)return false;
        if(id==9996101){if(count==weapons.size())return false;weapons[count++]=r;}
        for(auto p=begin;p<end;p+=4){
            std::uint32_t child=0;if(!Word(p,child)||!child)return false;
            bool seen=false;for(unsigned k=0;k<nodes;++k)seen=seen||tree[k]==child;
            if(seen)return false;
            if(nodes==tree.size())return false;tree[nodes++]=child;
        }
    }
    return effects::SameIdentity(owner,effects::Resolve(Read,nullptr,image_base,0));
}
}
void Start(std::uint32_t base) noexcept {
    if(mapping)return;
    FILETIME made{},exit{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&made,&exit,&kernel,&user))return;
    creation=(static_cast<std::uint64_t>(made.dwHighDateTime)<<32)|made.dwLowDateTime;
    wchar_t name[128]{};
    StringCchPrintfW(name,128,L"Local\\WonderBaneKatana-%lu-%llu",GetCurrentProcessId(),creation);
    mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Control),name);
    const auto error=GetLastError();
    if(!mapping || error==ERROR_ALREADY_EXISTS){if(mapping)CloseHandle(mapping);mapping=nullptr;return;}
    control=static_cast<Control*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Control)));
    if(!control){CloseHandle(mapping);mapping=nullptr;return;}
    Control initial{};initial.pid=GetCurrentProcessId();initial.creation=creation;
    std::memcpy(control,&initial,sizeof(initial));image_base=base;
}
void Stop() noexcept {
    EndScene();if(control)UnmapViewOfFile(control);if(mapping)CloseHandle(mapping);
    control=nullptr;mapping=nullptr;image_base=0;
}
void BeginScene(bool camera_available) noexcept {
    EndScene();count=0;
    if(!control)return;
    InterlockedExchange(&control->draws,0);InterlockedExchange(&control->matches,0);
    InterlockedExchange(&control->fire_draws,0);InterlockedExchange(&control->fire_reason,0);
    const auto before=InterlockedCompareExchange(&control->desired,0,0);
    float candidate=0;FireSettings requested{};std::memcpy(&candidate,&control->length,4);
    std::memcpy(&requested,&control->fire,sizeof(requested));MemoryBarrier();
    if(before!=InterlockedCompareExchange(&control->desired,0,0) || (before&1)
        || control->tag!=magic || control->version!=2 || control->size!=96
        || control->pid!=GetCurrentProcessId() || control->creation!=creation
        || !std::isfinite(candidate) || candidate<.6F || candidate>1.2F || !ValidFire(requested)){
        InterlockedExchange(&control->error,ERROR_INVALID_DATA);return;}
    length=candidate;fire=requested;seconds=static_cast<double>(GetTickCount64()%3600000)/1000.0;InterlockedExchange(&control->applied,before);
    InterlockedExchange(&control->error,0);
    if(!camera_available || !(context=wglGetCurrentContext()))return;
    if(!Collect()){count=0;InterlockedExchange(&control->error,ERROR_NOT_FOUND);return;}
    InterlockedExchange(&control->matches,static_cast<LONG>(count));active=true;
}
bool WantsDraws() noexcept {return active && control && (length!=1.F || fire.enabled);}
void EndScene() noexcept {active=false;count=0;owner={};scoped=1.F;scoped_index=-1;decorated={};context=nullptr;}
RenderScope::RenderScope(void* submission) noexcept:previous_(scoped),previous_index_(scoped_index) {
    scoped=1.F;scoped_index=-1;
    if(!control || !active || wglGetCurrentContext()!=context || (length==1.F && !fire.enabled))return;
    std::uint32_t render=0,id=0;
    if(!Word(static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(submission))+0x1c,render))return;
    int match=-1;for(unsigned n=0;n<count;++n)if(weapons[n]==render)match=static_cast<int>(n);
    if(match>=0 && Word(render+0x10,id) && id==9996101
        && effects::SameIdentity(owner,effects::Resolve(Read,nullptr,image_base,0))){scoped=length;scoped_index=match;}
}
RenderScope::~RenderScope(){scoped=previous_;scoped_index=previous_index_;}
DrawScale::DrawScale() noexcept {
    if(!control || !active || scaled || scoped_index<0 || (scoped==1.F && !fire.enabled) || wglGetCurrentContext()!=context || !AreNativeDrawQueriesSafe())return;
    GLint mode=0,depth=0,maximum=0,attrs=0,maxattrs=0;
    glGetIntegerv(GL_MATRIX_MODE,&mode);glGetIntegerv(GL_MODELVIEW_STACK_DEPTH,&depth);
    glGetIntegerv(GL_MAX_MODELVIEW_STACK_DEPTH,&maximum);
    glGetIntegerv(GL_ATTRIB_STACK_DEPTH,&attrs);glGetIntegerv(GL_MAX_ATTRIB_STACK_DEPTH,&maxattrs);
    if(mode!=GL_MODELVIEW || depth>=maximum || attrs>=maxattrs)return;
    // The native rigid-item path loads its model matrix before submission.
    // Post-multiply local Y around the model origin (the hand grip); never write game objects.
    glPushAttrib(GL_ENABLE_BIT);glEnable(GL_NORMALIZE);
    glPushMatrix();glScalef(1.F,scoped,1.F);pushed_=true;scaled=true;index_=scoped_index;
    if(control)InterlockedIncrement(&control->draws);
}
DrawScale::~DrawScale(){if(pushed_){
    if(fire.enabled && index_>=0 && !decorated[index_] && control && active
        && wglGetCurrentContext()==context && AreNativeDrawQueriesSafe()){
        const auto reason=DrawMoonfire(fire,seconds);
        InterlockedExchange(&control->fire_reason,static_cast<LONG>(reason));
        if(!reason){decorated[index_]=true;InterlockedIncrement(&control->fire_draws);}
    }
    glPopMatrix();glPopAttrib();scaled=false;
}}
}
