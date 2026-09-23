#include "effects_runtime.h"
#include "effects.h"
#include "reviewed_scene_boundary.h"
#include "effects_draw.h"
#include <gl/GL.h>
#include <strsafe.h>
#include <cstring>

namespace wonderbane::extension {
namespace {
#pragma pack(push,4)
struct Control {
    std::uint32_t magic=0x46584257U, version=1, size=256, pid=0;
    std::uint64_t creation=0;
    volatile LONG desired=0, applied=0, error=0, status_sequence=0;
    effects::Config config{};
    effects::Stats stats{};
    // Additive status in previously reserved bytes; config/stats offsets unchanged.
    std::uint32_t safety_version=1, presentation=0, suppressed_frames=0;
    std::uint32_t reserved[22]{};
};
#pragma pack(pop)
static_assert(sizeof(Control)==256);
static_assert(offsetof(Control,config)==40);
static_assert(offsetof(Control,stats)==124);
static_assert(offsetof(Control,safety_version)==156);
// Presentation: disabled, waiting for scene/attachment, permitted, suppressed, invalid.
enum : std::uint32_t { kDisabled, kWaiting, kPermitted, kSuppressed, kInvalid };
SRWLOCK g_lock=SRWLOCK_INIT;
HANDLE g_mapping=nullptr;
Control* g_control=nullptr;
effects::System g_system{};
effects::Geometry g_geometry{};
effects::Config g_config{};
ProcessIdentity g_identity{};
HGLRC g_context=nullptr;
std::uint32_t g_base=0;
bool g_suppressed=false;
bool Read(void*,std::uint32_t address,void* out,std::size_t size) {
    SIZE_T copied=0;
    return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const void*>(address),out,size,&copied) && copied==size;
}

}
DWORD StartEffects(const ProcessIdentity& identity) noexcept {
    bool reviewed=false;
    for (const auto* hash:kReviewedSceneExecutableHashes) reviewed|=GraphicsExecutableSha256Matches(hash);
    if (!reviewed || identity.process_id!=GetCurrentProcessId() || !identity.creation_filetime_utc) return ERROR_NOT_SUPPORTED;
    AcquireSRWLockExclusive(&g_lock);
    if (g_mapping) { ReleaseSRWLockExclusive(&g_lock); return ERROR_ALREADY_INITIALIZED; }
    wchar_t name[160]{};
    (void)StringCchPrintfW(name,160,L"Local\\WonderBaneEffects-%lu-%llu",identity.process_id,identity.creation_filetime_utc);
    HANDLE mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Control),name);
    DWORD error=GetLastError();
    if (mapping && error==ERROR_ALREADY_EXISTS) { CloseHandle(mapping); mapping=nullptr; }
    auto* control=mapping ? static_cast<Control*>(MapViewOfFile(mapping,FILE_MAP_READ|FILE_MAP_WRITE,0,0,sizeof(Control))):nullptr;
    if (mapping && !control) { error=GetLastError(); CloseHandle(mapping); }
    if (control) {
        *control=Control{}; control->pid=identity.process_id; control->creation=identity.creation_filetime_utc;
        g_mapping=mapping; g_control=control; g_identity=identity;
        g_system=effects::System{}; g_config={}; g_context=nullptr; g_suppressed=false;
        g_base=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr)));
        error=ERROR_SUCCESS;
    }
    ReleaseSRWLockExclusive(&g_lock); return error;
}
void StopEffects() noexcept {
    AcquireSRWLockExclusive(&g_lock);
    g_system.Clear(); g_geometry.count=0; g_config={}; g_context=nullptr; g_suppressed=false;
    if (g_control) UnmapViewOfFile(g_control);
    if (g_mapping) CloseHandle(g_mapping);
    g_control=nullptr; g_mapping=nullptr; g_identity={}; g_base=0;
    ReleaseSRWLockExclusive(&g_lock);
}
void DrawEffects(const GraphicsCameraState* camera, bool transparency_safe) noexcept {
    if (!TryAcquireSRWLockExclusive(&g_lock)) return;
    if (!g_control) { ReleaseSRWLockExclusive(&g_lock); return; }
    const LONG before=InterlockedCompareExchange(&g_control->desired,0,0);
    if (before && before!=g_control->applied) {
        effects::Config config{};
        std::memcpy(&config,&g_control->config,sizeof(config)); MemoryBarrier();
        const LONG after=InterlockedCompareExchange(&g_control->desired,0,0);
        if (before==after && !(before&1) && g_control->magic==0x46584257U
            && g_control->version==1 && g_control->size==256 && g_control->pid==g_identity.process_id
            && g_control->creation==g_identity.creation_filetime_utc && effects::Validate(config)) {
            if (config.attachment!=g_config.attachment || config.height!=g_config.height) g_system.Clear();
            if (!(config.flags&1U)) g_suppressed=false;
            g_config=config; InterlockedExchange(&g_control->applied,before); g_control->error=0;
        } else { g_config.flags=0; g_system.Clear(); g_control->error=ERROR_INVALID_DATA; }
    }
    const bool requested=(g_config.flags&1U)!=0;
    if (requested && !transparency_safe) g_suppressed=true;
    const bool suppressed=requested && g_suppressed;
    const auto current=wglGetCurrentContext();
    if (!camera || !current || current!=g_context) g_system.Clear();
    g_context=current;
    const auto attachment=(!suppressed && camera && current && requested)
        ? effects::Resolve(Read,nullptr,g_base,g_config.attachment):effects::Attachment{};
    auto simulation=g_config;
    if (suppressed) simulation.flags=0; // Step cancels the current burst as it clears history.
    g_system.Step(simulation,attachment,static_cast<double>(GetTickCount64())/1000.0);
    g_geometry.count=0;
    if (!suppressed && camera && current && requested && attachment.valid) {
        const auto vec=[](const float* p) { return effects::Vec{p[0],p[1],p[2]}; };
        const auto& v=camera->view_matrix;
        g_system.Build(g_config,vec(camera->position),{v[0],v[4],v[8]},vec(camera->up),vec(camera->forward),g_geometry);
        if (g_geometry.count && !RenderEffectsGeometry(g_config,g_geometry,*camera)) ++g_system.stats.render_rejected;
    }
    InterlockedIncrement(&g_control->status_sequence);
    g_control->stats=g_system.stats;
    g_control->safety_version=1;
    g_control->presentation=g_control->error ? kInvalid : !requested ? kDisabled
        : suppressed ? kSuppressed : attachment.valid ? kPermitted : kWaiting;
    if (suppressed && g_control->suppressed_frames!=UINT32_MAX) ++g_control->suppressed_frames;
    MemoryBarrier();
    InterlockedIncrement(&g_control->status_sequence);
    ReleaseSRWLockExclusive(&g_lock);
}
}
