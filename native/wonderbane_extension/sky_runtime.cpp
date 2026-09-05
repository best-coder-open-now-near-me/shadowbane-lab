#include "sky_runtime.h"
#include "scene_context.h"
#include "sky.h"
#include "sky_binding.h"
#include "sky_asset_identity.h"
#include "render_lifetime.h"
#include "import_hook.h"
#include "effects.h"
#include <gl/GL.h>
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
namespace wonderbane::extension {
namespace {
struct SkyControl {
    std::uint32_t magic=0x534b4257U,version=1,size=136,pid=0;
    std::uint64_t creation=0;
    volatile LONG desired=0,applied=0,error=0,status=0;
    sky::Settings settings{};
    std::uint32_t ready=0,painted=0,refused=0,suppressed=0,reason=0,microseconds=0,asset=0,reserved=0;
    unsigned char asset_hash[32]{};
};
static_assert(sizeof(SkyControl)==136);
static_assert(offsetof(SkyControl,settings)==40);
HANDLE sky_mapping=nullptr;
SkyControl* sky_control=nullptr;
sky::Asset sky_asset{};
thread_local sky::Settings sky_settings{};
std::uint32_t sky_base=0;
std::uint64_t sky_generation=1,sky_creation=0;
std::uint32_t* sky_slot=nullptr;
PVOID volatile sky_original=nullptr;
bool sky_running=false;
SRWLOCK sky_status_lock=SRWLOCK_INIT;
thread_local sky::Authority sky_authority;
thread_local effects::Attachment sky_actor;
using NativeSky=void(__thiscall*)(void*);
bool ReadSky(void*,std::uint32_t address,void* out,std::size_t bytes) {
    SIZE_T copied=0;return address>=0x10000&&address<=0x7FFEFFFF&&bytes<=0x7FFEFFFF-address
        &&ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const void*>(address),out,bytes,&copied)&&copied==bytes;
}
// All runtime state access is inside the shared callback admission domain.
// Control writers use their own sequence; no native lock is held across original GL calls.
void PollSky() noexcept {
    if(!sky_control)return;
    const LONG before=InterlockedCompareExchange(&sky_control->desired,0,0);
    sky::Settings next{};std::memcpy(&next,&sky_control->settings,sizeof(next));MemoryBarrier();
    const LONG after=InterlockedCompareExchange(&sky_control->desired,0,0);
    if(before!=after||(before&1)||sky_control->magic!=0x534b4257U||sky_control->version!=1
        ||sky_control->size!=136||sky_control->pid!=GetCurrentProcessId()||sky_control->creation!=sky_creation
        ||!sky::Valid(next)){
        sky_settings={};InterlockedExchange(&sky_control->error,ERROR_INVALID_DATA);return;
    }
    sky_settings=next;InterlockedExchange(&sky_control->applied,before);InterlockedExchange(&sky_control->error,0);
}
void __fastcall NativeSkyDraw(void* self,void*) noexcept {
    const RenderCallbackLease lease;
    const auto original=reinterpret_cast<NativeSky>(InterlockedCompareExchangePointer(&sky_original,nullptr,nullptr));
    if(!original)return;
    const auto caller=reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    const auto context=reinterpret_cast<std::uintptr_t>(wglGetCurrentContext());
    std::uint32_t table=0;
    const bool replace=sky_running&&sky_authority.painted&&sky_authority.generation==sky_generation
        &&context==sky_authority.context&&IsReviewedSceneCall(caller,sky_base,0x5524df)
        &&ReadSky(nullptr,static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(self)),&table,4)
        &&table==sky_base+0x1162b34&&effects::SameIdentity(sky_actor,effects::Resolve(ReadSky,nullptr,sky_base,0));
    if(replace){if(sky_control)InterlockedIncrement(reinterpret_cast<volatile LONG*>(&sky_control->suppressed));return;}
    original(self);
}
bool LoadSkyAsset() noexcept {
    HMODULE module=nullptr;
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&LoadSkyAsset),&module))return false;
    HRSRC resource=FindResourceW(module,MAKEINTRESOURCEW(201),RT_RCDATA);
    if(!resource||SizeofResource(module,resource)!=sizeof(sky::Asset))return false;
    const void* bytes=LockResource(LoadResource(module,resource));
    if(!bytes||!sky::Hash(bytes,sizeof(sky::Asset),sky::kAssetHash))return false;
    std::memcpy(&sky_asset,bytes,sizeof(sky_asset));return sky::ValidAsset(sky_asset);
}
}
DWORD StartSky(std::uint8_t* image,std::size_t size,const char* hash) noexcept {
    const RenderLifecycleMutation mutation;
    if(sky_mapping||sky_slot)return ERROR_ALREADY_INITIALIZED;
    sky_running=false;++sky_generation;sky_settings={};
    sky_base=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(image));
    if(!IsReviewedSceneExecutable(hash)||!sky::ReviewedBackground(image,size,sky_base))return ERROR_REVISION_MISMATCH;
    if(!LoadSkyAsset())return ERROR_INVALID_DATA;
    const DWORD context_result=StartSceneContextObservation(image,size);
    if(context_result!=ERROR_SUCCESS)return context_result;
    FILETIME creation{},exit{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user))return GetLastError();
    sky_creation=(static_cast<std::uint64_t>(creation.dwHighDateTime)<<32)|creation.dwLowDateTime;
    wchar_t name[128]{};StringCchPrintfW(name,128,L"Local\\WonderBaneSky-%lu-%llu",GetCurrentProcessId(),sky_creation);
    sky_mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(SkyControl),name);
    const DWORD error=GetLastError();
    if(!sky_mapping)return error;
    if(error==ERROR_ALREADY_EXISTS){CloseHandle(sky_mapping);sky_mapping=nullptr;return error;}
    sky_control=static_cast<SkyControl*>(MapViewOfFile(sky_mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(SkyControl)));
    if(!sky_control){const auto e=GetLastError();CloseHandle(sky_mapping);sky_mapping=nullptr;return e;}
    *sky_control=SkyControl{};sky_control->pid=GetCurrentProcessId();sky_control->creation=sky_creation;
    sky_control->asset=1;
    for(unsigned n=0;n<32;++n){
        const auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
        sky_control->asset_hash[n]=static_cast<unsigned char>(digit(sky::kAssetHash[n*2])*16+digit(sky::kAssetHash[n*2+1]));
    }
    auto* slot=reinterpret_cast<std::uint32_t*>(image+0x1162b40);
    InterlockedExchangePointer(&sky_original,reinterpret_cast<PVOID>(sky_base+0xa213));
    const DWORD result=ReplaceImportAddressSlot(slot,sky_base+0xa213,
        static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&NativeSkyDraw)));
    if(result!=ERROR_SUCCESS){UnmapViewOfFile(sky_control);CloseHandle(sky_mapping);sky_control=nullptr;sky_mapping=nullptr;return result;}
    sky_slot=slot;sky_running=true;sky_control->ready=1;return ERROR_SUCCESS;
}
void StopSky() noexcept {
    const RenderLifecycleMutation mutation;
    sky_running=false;++sky_generation;
    if(sky_slot&&ReplaceImportAddressSlot(sky_slot,
        static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&NativeSkyDraw)),
        static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(InterlockedCompareExchangePointer(&sky_original,nullptr,nullptr))))==ERROR_SUCCESS)sky_slot=nullptr;
    // Retain original call-through; a dispatched callback can enter after restoration.
    // No GPU objects exist. RCDATA belongs to the pinned extension module.
    if(sky_control)UnmapViewOfFile(sky_control);if(sky_mapping)CloseHandle(sky_mapping);
    sky_control=nullptr;sky_mapping=nullptr;sky_settings={};sky_authority.Reset();sky_actor={};
}
void ObserveSkyCameraUpload(std::uintptr_t caller,bool legal) noexcept {
    if(!sky_running||!legal||(!IsReviewedSceneCall(caller,sky_base,0x51b1df)
        &&!IsReviewedSceneCall(caller,sky_base,0x51bbb2)))return;
    sky_authority.Reset();sky_actor={};
    GLint mode=0,depth=0,list=0;glGetIntegerv(GL_MATRIX_MODE,&mode);
    glGetIntegerv(GL_MODELVIEW_STACK_DEPTH,&depth);glGetIntegerv(GL_LIST_INDEX,&list);
    if(mode!=GL_MODELVIEW||depth!=1||list)return;
    float view[16]{};glGetFloatv(GL_MODELVIEW_MATRIX,view);
    sky_authority.Upload(view,reinterpret_cast<std::uintptr_t>(wglGetCurrentContext()),sky_generation);
}
void BeginSkyBackground(const GraphicsCameraState* camera,bool scene) noexcept {
    if(!sky_running)return;
    if(!TryAcquireSRWLockExclusive(&sky_status_lock)){DiscardSkyScene();return;}
    PollSky();const auto context=reinterpret_cast<std::uintptr_t>(wglGetCurrentContext());
    sky_actor=effects::Resolve(ReadSky,nullptr,sky_base,0);
    const bool authority=sky_authority.Consume(camera,context,sky_generation,scene&&sky_actor.valid);
    if(sky_control){InterlockedIncrement(&sky_control->status);sky_control->painted=0;sky_control->reason=0;}
    if(sky_settings.enabled){
        LARGE_INTEGER begin{},end{},frequency{};QueryPerformanceCounter(&begin);
        const bool painted=authority&&camera&&sky::Render(sky_asset,sky_settings,*camera);
        QueryPerformanceCounter(&end);QueryPerformanceFrequency(&frequency);
        sky_authority.painted=painted;
        if(sky_control){sky_control->painted=painted?1:0;sky_control->reason=painted?0:authority?2:1;
            if(!painted)++sky_control->refused;
            sky_control->microseconds=frequency.QuadPart>0?static_cast<std::uint32_t>((end.QuadPart-begin.QuadPart)*1000000/frequency.QuadPart):0;}
    }
    if(sky_control){MemoryBarrier();InterlockedIncrement(&sky_control->status);}
    ReleaseSRWLockExclusive(&sky_status_lock);
}
void DiscardSkyScene() noexcept {sky_authority.Reset();sky_actor={};}
void EndSkyFrame() noexcept {
    PollSky();DiscardSkyScene();
}
}
