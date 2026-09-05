#include "selected_cue_runtime.h"
#include "selected_cue.h"
#include "selected_cue_gpu.h"
#include "selected_cue_binding.h"
#include "effects.h"
#include "import_hook.h"
#include "reviewed_scene_boundary.h"
#include <strsafe.h>
#include <gl/GL.h>
#include <array>
#include <cstring>

namespace wonderbane::extension {
namespace {
constexpr std::uint32_t kMagic=0x55434257U;
#pragma pack(push,4)
struct Control {
    std::uint32_t magic=kMagic,version=1,size=sizeof(Control),pid=0,creation_low=0,creation_high=0;
    volatile LONG sequence=0,applied=0,rejected=0,error=0;
    cue::Settings settings{};
    volatile LONG binding=0,owned_draws=0,render_error=0,observation_error=0;
};
#pragma pack(pop)
static_assert(sizeof(Control)==88);
static_assert(offsetof(Control,settings)==40);
SRWLOCK lock=SRWLOCK_INIT;
HANDLE mapping=nullptr;
Control* control=nullptr;
volatile LONG running=0;
std::uint32_t base=0;
std::uint64_t expected_creation=0;
std::uint32_t* slot=nullptr;
std::uint32_t* context_slot=nullptr;
PVOID volatile original_context=nullptr;
using MakeCurrent=BOOL(WINAPI*)(HDC,HGLRC);
using Render=void(__thiscall*)(void*);
PVOID volatile original=nullptr;
thread_local cue::Settings settings{};
thread_local effects::Attachment attachment{};
thread_local std::array<std::uint32_t,128> renders{};
thread_local std::size_t render_count=0;
thread_local cue::Tracker tracker;
thread_local cue::Direction direction;
thread_local bool scene=false,finished=false,mask_failed=false;
thread_local unsigned nesting=0,owned=0;
bool Read(void*,std::uint32_t address,void* data,std::size_t bytes) {
    if(address<0x10000 || address>0x7FFEFFFF || bytes>0x7FFEFFFF-address)return false;
    SIZE_T copied=0;return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const void*>(address),
        data,bytes,&copied) && copied==bytes;
}
template<class T> bool Field(std::uint32_t p,std::uint32_t offset,T& v) noexcept {
    return p>=0x10000 && p<=0x7FFEFFFF-offset && Read(nullptr,p+offset,&v,sizeof(v));
}
effects::Attachment Selected() noexcept {
    auto result=effects::Resolve(Read,nullptr,base,1);
    std::uint32_t table=0;
    if(!result.valid || !Field(result.actor,0,table) || table!=base+0x114165c) return {};
    return result;
}
bool CollectRenders() noexcept {
    render_count=0;
    if(!Field(attachment.actor,0xc0,renders[0]) || !renders[0])return false;
    render_count=1;
    for(std::size_t n=0;n<render_count;++n){
        std::uint32_t begin=0,end=0;
        if(!Field(renders[n],0x3c,begin) || !Field(renders[n],0x40,end)
            || end<begin || (end-begin)%4 || (end-begin)/4>renders.size())return false;
        for(auto p=begin;p<end;p+=4){
            std::uint32_t child=0;if(!Field(p,0,child) || !child)return false;
            bool seen=false;for(std::size_t i=0;i<render_count;++i)seen=seen||renders[i]==child;
            if(seen)continue;
            if(render_count==renders.size())return false;
            renders[render_count++]=child;
        }
    }
    return true;
}
void Status(LONG draw_count,LONG render_error,LONG observation_error) noexcept {
    if(!TryAcquireSRWLockShared(&lock))return;
    if(control){InterlockedExchange(&control->owned_draws,draw_count);
        InterlockedExchange(&control->render_error,render_error);
        InterlockedExchange(&control->observation_error,observation_error);}
    ReleaseSRWLockShared(&lock);
}
bool Poll() noexcept {
    if(!TryAcquireSRWLockShared(&lock))return false;
    bool valid=false;
    if(control){
        LONG before=InterlockedCompareExchange(&control->sequence,0,0);
        cue::Settings candidate{};std::memcpy(&candidate,&control->settings,sizeof(candidate));MemoryBarrier();
        LONG after=InterlockedCompareExchange(&control->sequence,0,0);
        valid=before==after && !(before&1) && cue::ValidSettings(candidate)
            && control->magic==kMagic && control->version==1 && control->size==sizeof(Control)
            && control->pid==GetCurrentProcessId()
            && ((static_cast<std::uint64_t>(control->creation_high)<<32)|control->creation_low)==expected_creation;
        if(valid){settings=candidate;InterlockedExchange(&control->applied,before);InterlockedExchange(&control->error,0);}
        else{InterlockedExchange(&control->rejected,before);InterlockedExchange(&control->error,ERROR_INVALID_DATA);}
    }
    ReleaseSRWLockShared(&lock);return valid;
}
bool StillSelected() noexcept {
    std::uint32_t root=0;
    return effects::SameIdentity(attachment,Selected()) && render_count
        && Field(attachment.actor,0xc0,root) && root==renders[0];
}
BOOL WINAPI CueMakeCurrent(HDC dc,HGLRC context) noexcept {
    const auto call=reinterpret_cast<MakeCurrent>(InterlockedCompareExchangePointer(&original_context,nullptr,nullptr));
    if(!call)return FALSE;
    if(context!=wglGetCurrentContext())ReleaseSelectedCueContext();
    return call(dc,context);
}
void __fastcall OwnedRender(void* self,void*) noexcept {
    const auto draw=reinterpret_cast<Render>(InterlockedCompareExchangePointer(&original,nullptr,nullptr));
    if(!draw)return;
    if(!scene || !InterlockedCompareExchange(&running,0,0) || nesting){draw(self);return;}
    std::uint32_t render=0;bool match=false;
    if(Field(static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(self)),0x1c,render))
        for(std::size_t n=0;n<render_count;++n)match=match || renders[n]==render;
    if(!match){draw(self);return;}
    if(!StillSelected()){DiscardSelectedCueScene();draw(self);return;}
    if(owned>=128){mask_failed=true;cue::DiscardMask();draw(self);return;}
    ++nesting;
    const bool captured=!mask_failed && cue::BeforeOwnedDraw();
    draw(self); // Exactly one original call. No actor/animation replay.
    if(captured && StillSelected()){
        if(!cue::AfterOwnedDraw()){mask_failed=true;cue::DiscardMask();}
    }else {mask_failed=true;cue::DiscardMask();}
    --nesting;++owned;
}
}
DWORD StartSelectedCue(std::uint8_t* image,std::size_t size,const char* hash) noexcept {
    AcquireSRWLockExclusive(&lock);
    if(mapping){ReleaseSRWLockExclusive(&lock);return ERROR_ALREADY_INITIALIZED;}
    FILETIME creation{},exit{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user)){
        auto error=GetLastError();ReleaseSRWLockExclusive(&lock);return error;}
    const auto time=(static_cast<std::uint64_t>(creation.dwHighDateTime)<<32)|creation.dwLowDateTime;
    wchar_t name[128]{};StringCchPrintfW(name,128,L"Local\\WonderBaneSelectedCue-%lu-%llu",GetCurrentProcessId(),time);
    mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Control),name);
    auto error=GetLastError();
    if(!mapping || error==ERROR_ALREADY_EXISTS){if(mapping)CloseHandle(mapping);mapping=nullptr;
        ReleaseSRWLockExclusive(&lock);return error;}
    control=static_cast<Control*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Control)));
    if(!control){error=GetLastError();CloseHandle(mapping);mapping=nullptr;ReleaseSRWLockExclusive(&lock);return error;}
    expected_creation=time;
    Control initial{};initial.pid=GetCurrentProcessId();initial.creation_low=creation.dwLowDateTime;
    initial.creation_high=creation.dwHighDateTime;std::memcpy(control,&initial,sizeof(initial));
    base=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(image));
    if(!IsReviewedSceneExecutable(hash) || !cue::ReviewedBinding(image,size,base))error=ERROR_REVISION_MISMATCH;
    else{
        context_slot=FindImportAddressSlot(image,size,"opengl32.dll","wglMakeCurrent");
        if(!context_slot)error=ERROR_PROC_NOT_FOUND;
        else {
            InterlockedExchangePointer(&original_context,reinterpret_cast<void*>(*context_slot));
            error=ReplaceImportAddressSlot(context_slot,*context_slot,
                static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&CueMakeCurrent)));
        }
        slot=reinterpret_cast<std::uint32_t*>(image+0x1149ed4);
        InterlockedExchangePointer(&original,reinterpret_cast<PVOID>(base+0x26d91));
        if(error==ERROR_SUCCESS)error=ReplaceImportAddressSlot(slot,base+0x26d91,static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&OwnedRender)));
        if(error==ERROR_SUCCESS){InterlockedExchange(&running,1);InterlockedExchange(&control->binding,1);}
    }
    InterlockedExchange(&control->error,static_cast<LONG>(error));
    ReleaseSRWLockExclusive(&lock);return error;
}
void StopSelectedCue() noexcept {
    InterlockedExchange(&running,0);
    if(slot){const auto replacement=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&OwnedRender));
        if(ReplaceImportAddressSlot(slot,replacement,base+0x26d91)==ERROR_SUCCESS)slot=nullptr;}
    if(context_slot){
        const auto replacement=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&CueMakeCurrent));
        const auto prior=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(InterlockedCompareExchangePointer(&original_context,nullptr,nullptr)));
        if(ReplaceImportAddressSlot(context_slot,replacement,prior)==ERROR_SUCCESS)context_slot=nullptr;
    }
    // Keep original callable for an already-entered wrapper. Extension lifetime
    // is pinned by the existing startup path; do not null a live trampoline.
    AcquireSRWLockExclusive(&lock);
    if(control)UnmapViewOfFile(control);if(mapping)CloseHandle(mapping);
    control=nullptr;mapping=nullptr;ReleaseSRWLockExclusive(&lock);
    DiscardSelectedCueScene();cue::ReleaseMask();
}
void DiscardSelectedCueScene() noexcept {scene=false;attachment={};render_count=0;tracker.Reset();cue::DiscardMask();}
void EndSelectedCueFrame() noexcept {if(!finished)DiscardSelectedCueScene();finished=false;}
void ReleaseSelectedCueContext() noexcept {DiscardSelectedCueScene();cue::ReleaseMask();}
void BeginSelectedCueScene(const GraphicsCameraState* camera) noexcept {
    scene=false;owned=0;mask_failed=false;cue::DiscardMask();
    if(!InterlockedCompareExchange(&running,0,0) || !Poll() || !settings.enabled){
        DiscardSelectedCueScene();cue::ReleaseMask();return;}
    attachment=Selected();
    if(!attachment.valid || !CollectRenders() || !camera){DiscardSelectedCueScene();Status(0,0,1);return;}
    const cue::Identity identity{attachment.actor,attachment.type,attachment.uuid,attachment.zone,renders[0],
        attachment.component,attachment.location,attachment.zone_type,attachment.zone_uuid};
    const float position[]{attachment.position.x,attachment.position.y,attachment.position.z};
    direction=tracker.Update(identity,position,camera,true);
    scene=direction.available;
    mask_failed=!(scene && cue::BeginMask());Status(0,mask_failed?1:0,0);
}
void FinishSelectedCueScene(const GraphicsCameraState* camera) noexcept {
    if(!scene || !camera || !InterlockedCompareExchange(&running,0,0)
        || !StillSelected()){DiscardSelectedCueScene();return;}
    const bool ok=cue::CompositeMask(settings,direction);Status(static_cast<LONG>(owned),ok && !mask_failed?0:1,0);
    scene=false;finished=true;attachment={};render_count=0;
}
}
