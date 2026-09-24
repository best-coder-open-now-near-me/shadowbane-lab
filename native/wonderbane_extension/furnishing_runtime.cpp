#include "furnishing_runtime.h"
#include "furnishing_controls.h"
#include "furnishing_events.h"
#include "furnishing_frame.h"
#include "furnishing_native_calls.h"
#include "furnishing_render_owner.h"
#include "furnishing_resources.h"
#include "furnishing_pose.h"
#include "native_owner_services.h"
#include "movement_lifetime.h"
#include "movement_native_ui.h"
#include "cel_shading.h"
#include "render_lifetime.h"
#include "scene_context.h"
#include <gl/GL.h>
#include <new>
#include <optional>

namespace wonderbane::extension::furnishing {
namespace {
struct Runtime;
std::atomic<Runtime*> runtime{nullptr};
struct Runtime {
    NativeCalls native;
    movement::NativeUi ui;
    std::optional<SelectionCapture> capture;
    std::optional<RenderResources> resources;
    std::optional<RenderOwner> render;
    PreviewControls controls{{this,&Action,&UiCurrent,&Contains}};
    FrameGate frame;
    std::atomic<bool> enabled{false};
    std::atomic<DWORD> owner_thread_id{0};
    movement::NativeScene scene{};
    Address root=0;
    HWND window=nullptr;
    DWORD thread=0;
    Selection selected{},requested{};
    std::array<float,3> point{};
    unsigned turns=0;
    bool bound=false,busy=false,terminal=false,active=false,start_pending=false,posed=false,held=false;
    const wchar_t* status=L"Preview only - select Preview, then move over the floor plan";
    static Runtime& Self(void* p) noexcept { return *static_cast<Runtime*>(p); }
    static bool Read(void*,Address at,void* out,std::size_t n) noexcept { return NativeCalls::Read(at,out,n); }
    static bool Owner(void* p) noexcept { return Self(p).native.Owner(); }
    static bool Watched(void* p,const SelectionCapture::Owner& owner) noexcept {
        auto& s=Self(p);
        return s.native.Owner() && owner.root==s.root && owner.actor==s.scene.actor && owner.parent==s.scene.parent
            && owner.epoch==s.scene.epoch && movement::NativeMovementLifetimeCurrent(s.scene);
    }
    bool Capture(Selection& out) noexcept {
        return bound && native.Owner() && capture && scene.window==root
            && capture->Capture({root,static_cast<Address>(scene.actor),static_cast<Address>(scene.parent),scene.epoch},out);
    }
    bool Current(const Selection& old) noexcept {
        Selection next{}; return !terminal && enabled.load(std::memory_order_acquire) && Capture(next) && next.SameIdentity(old);
    }
    static bool UiCurrent(void* p,const Selection& old) noexcept { return Self(p).Current(old); }
    static PreviewControls::Hit Contains(void* p,const Selection& s,int x,int y) noexcept {
        auto& self=Self(p); POINT mapped{};
        const auto result=movement::NativeClientPoint(self.native.Base(),self.root,self.window,{x,y},mapped);
        if(result==movement::NativePointResult::unavailable) { return PreviewControls::Hit::unavailable; }
        return result==movement::NativePointResult::valid && LayoutContains(s,mapped.x,mapped.y)
            ?PreviewControls::Hit::inside:PreviewControls::Hit::outside;
    }
    static bool SelectionCurrent(void* p,const Selection& old) noexcept { return Self(p).Current(old); }
    static bool ResourceCurrent(void* p) noexcept {
        auto& s=Self(p); return !s.terminal && s.enabled.load(std::memory_order_acquire)
            && s.native.Owner() && movement::NativeMovementLifetimeCurrent(s.scene);
    }
    static bool Texture(void* p,std::uint32_t name,std::uint32_t target) noexcept {
        return Owner(p) && target==GL_TEXTURE_2D && glIsTexture(name)==GL_TRUE;
    }
    static bool Source(void* p,const Selection& v) noexcept { return Self(p).resources->Source(v); }
    static bool Retain(void* p,Address v,Address* slot) noexcept { return Self(p).native.RetainModel(v,slot); }
    static bool Clone(void* p,Address v,Address* slot) noexcept { return Self(p).native.Clone(v,slot); }
    static bool Release(void* p,Address* slot) noexcept { return Self(p).native.Release(slot); }
    static bool Private(void* p,const Selection& s,Address clone,Address* renders,std::size_t cap,std::size_t* count) noexcept {
        return Self(p).resources->Private(s,clone,renders,cap,count);
    }
    static bool Compose(void* p,Address clone,const Transform& pose) noexcept { return Self(p).native.Compose(clone,pose); }
    static bool Enqueue(void* p,Address clone,Address queue) noexcept { return Self(p).native.Enqueue(clone,queue); }
    static bool Pool(void* p,QueueReceipt::Pool& pool) noexcept { return Self(p).native.Pool(pool); }
    static bool Erase(void* p,Address queue,Address node) noexcept { return Self(p).native.Erase(queue,node); }
    static bool Wrapper(void* p,Address wrapper,Address object) noexcept { return Self(p).resources->Wrapper(wrapper,object); }
    bool Configure() noexcept {
        if(!native.Configure()) { return false; }
        capture.emplace(SelectionCapture::Access{this,&Read,&Watched,native.Base()});
        resources.emplace(RenderResources::Access{this,&Read,&ResourceCurrent,&Texture,native.Base()});
        render.emplace(RenderOwner::Operations{this,&Owner,&SelectionCurrent,&Source,&Retain,&Clone,&Release,&Private,&Compose,&Enqueue,&Pool,&Wrapper},
            QueueReceipt::Access{this,&Read,&Owner,&Erase,native.Base()+0x1149d38});
        return true;
    }
    static void Action(void* p,PreviewControls::Action action) noexcept {
        auto& s=Self(p);
        switch(action) {
        case PreviewControls::Action::start:
            if(!s.active && !s.terminal && s.Current(s.selected)) {
                s.requested=s.selected; s.start_pending=true; s.active=true; s.posed=s.held=false; s.turns=0;
            } break;
        case PreviewControls::Action::left: if(s.active) { s.turns=(s.turns+3)%4; } break;
        case PreviewControls::Action::right: if(s.active) { s.turns=(s.turns+1)%4; } break;
        case PreviewControls::Action::cancel: s.Cancel(); break;
        case PreviewControls::Action::hold: if(s.active && s.posed) { s.held=!s.held; } break;
        }
    }
    void Cancel() noexcept {
        const bool was_active=active || start_pending;
        active=start_pending=posed=held=false;
        if(render) { render->Close(); }
        // Native cleanup is deferred to Update or the matching drain, never a UI callback.
        if(was_active) { status=L"Preview cancelled - select Preview to start again"; }
    }
    void Fail() noexcept {
        Cancel(); terminal=true; frame.Invalidate(); render->InvalidateContext();
        status=L"Preview unavailable for this session";
    }
    void Cleanup() noexcept {
        if(render->CurrentState()==RenderOwner::State::owned) { (void)render->Clear(); }
        if(render->CurrentState()==RenderOwner::State::quarantined) { Fail(); }
    }
    void Update(void* receiver,HWND hwnd) noexcept {
        const auto owner=owner_thread_id.load(std::memory_order_acquire);
        if((owner && owner!=GetCurrentThreadId()) || busy) { return; }
        if(terminal) {
            Selection fresh{};
            if(Capture(fresh)) { controls.Show(&fresh,false,status); } else { controls.Hide(); }
            return;
        }
        if(!bound) {
            if(!enabled.load(std::memory_order_acquire) || !native.Bind(hwnd)) { return; }
            bound=true; window=hwnd; thread=GetCurrentThreadId();
            owner_thread_id.store(thread,std::memory_order_release);
            if(!ui.Bind(hwnd) || !controls.Bind(hwnd)) { Fail(); return; }
        }
        if(thread!=GetCurrentThreadId() || hwnd!=window || !native.Owner()) { return; }
        busy=true;
        struct Reset { bool& busy; ~Reset() { busy=false; } } reset{busy};
        if(frame.Draining()) { Fail(); controls.Hide(); return; }
        if(!enabled.load(std::memory_order_acquire)) { Cancel(); Cleanup(); frame.Invalidate(); controls.Hide(); return; }
        root=reinterpret_cast<Address>(receiver);
        movement::NativeScene next{}; Selection fresh{};
        const bool observed=movement::ReadNativeMovementLifetime(next) && movement::NativeMovementLifetimeCurrent(next);
        scene=observed?next:movement::NativeScene{};
        if(!observed || !Capture(fresh)) { Cancel(); Cleanup(); controls.Hide(); return; }
        if(active && !fresh.SameIdentity(requested)) { Cancel(); }
        selected=fresh;
        if(!active) { Cleanup(); controls.Show(&selected,false,status); return; }
        if(start_pending) {
            Cleanup(); start_pending=false;
            if(terminal || !render->Open() || !render->Acquire(selected)) {
                Cancel(); Cleanup(); status=terminal?L"Preview unavailable for this session":L"This item's loaded model is unavailable for preview";
                controls.Show(&selected,false,status); return;
            }
        }
        POINT cursor{}; movement::NativeUiState ui_state{};
        const bool focused=GetForegroundWindow()==window;
        if(!focused) { Cancel(); Cleanup(); controls.Hide(); return; }
        if(!GetCursorPos(&cursor) || !ScreenToClient(window,&cursor) || !ui.Snapshot(cursor,ui_state)
            || ui_state.global_owned || ui_state.keyboard_owned || ui_state.camera_gesture) {
            Cancel(); Cleanup(); controls.Show(&selected,false,status); return;
        }
        if(!held && ui_state.pointer_hud==selected.hud && LayoutContains(selected,ui_state.native_point.x,ui_state.native_point.y)) {
            std::array<float,3> candidate{};
            const auto result=Current(selected)?native.Floor(selected,ui_state.native_point.x,ui_state.native_point.y,candidate):NativeCalls::FloorResult::unavailable;
            if(result==NativeCalls::FloorResult::fault) { Fail(); controls.Show(&selected,false,status); return; }
            posed=result==NativeCalls::FloorResult::hit && Current(selected);
            if(posed) { point=candidate; }
        }
        if(posed) {
            Transform pose{};
            if(!CandidatePose(selected,point,turns,pose) || !render->Pose(pose)) {
                Cancel(); Cleanup(); status=L"Preview unavailable at this building or floor";
            }
        }
        if(active) { status=held?L"Position held - rotate, or click the floor plan to follow again"
            :posed?L"Preview only - click floor plan to hold; Esc cancels":L"Move over the selected floor plan to preview"; }
        controls.Show(&selected,active,status);
    }
    void Clear(bool main) noexcept {
        if(owner_thread_id.load(std::memory_order_acquire)!=GetCurrentThreadId() || !bound || !native.Owner()) { return; }
        frame.Clear(main && !terminal && enabled.load(std::memory_order_acquire));
        if(frame.Broken()) { Fail(); }
    }
    void Push() noexcept {
        if(owner_thread_id.load(std::memory_order_acquire)!=GetCurrentThreadId() || !bound || !native.Owner()) { return; }
        const auto ticket=frame.Enter();
        if(!ticket || !active || !posed || terminal || !enabled.load(std::memory_order_acquire)) { return; }
        GLint mode=0,list=0; glGetIntegerv(GL_MATRIX_MODE,&mode); glGetIntegerv(GL_LIST_INDEX,&list);
        if(!SceneMatrixObservationCurrent() || mode!=GL_MODELVIEW || list || !Current(requested)) { Cancel(); return; }
        (void)render->Submit(root+0xfc,ticket);
        if(render->CurrentState()==RenderOwner::State::quarantined) { Fail(); }
    }
    void Pop() noexcept {
        if(owner_thread_id.load(std::memory_order_acquire)!=GetCurrentThreadId() || !bound || !native.Owner()) { return; }
        Address shader=1;
        const bool clear=NativeCalls::Read(native.Base()+0x16a9dd4,&shader,sizeof(shader)) && !shader;
        const auto ticket=frame.Leave(clear);
        if(frame.Broken()) { Fail(); return; }
        if(ticket && render->CurrentState()==RenderOwner::State::submitted && !render->Retire(ticket)) { Fail(); }
    }
    void Lost() noexcept {
        if(owner_thread_id.load(std::memory_order_acquire)!=GetCurrentThreadId() || !bound) { return; }
        Cancel();
        if(native.Owner() && !frame.Draining()) { Cleanup(); }
        // No rebinding after loss, including failed context switches. Any receipt
        // without a proven outer completion keeps its bounded references pinned.
        terminal=true; frame.Invalidate(); render->InvalidateContext(); controls.Hide();
    }
};
void MatrixChanged(bool push,std::uintptr_t caller) noexcept {
    const RenderCallbackLease lease;
    auto* s=runtime.load(std::memory_order_acquire);
    if(!s) { return; }
    if(push && caller==s->native.Base()+0x79c73e) { s->Push(); }
    if(!push && caller==s->native.Base()+0x79c7f7) { s->Pop(); }
}
void OwnerUpdate(void* root,HWND window) noexcept {
    const RenderCallbackLease lease;
    if(auto* s=runtime.load(std::memory_order_acquire)) { s->Update(root,window); }
}
void OwnerRetire(HWND window) noexcept {
    const RenderCallbackLease lease;
    if(auto* s=runtime.load(std::memory_order_acquire); s && s->owner_thread_id.load(std::memory_order_acquire)==GetCurrentThreadId() && s->window==window) { s->Lost(); s->controls.Retire(); }
}
void RendererChanged(bool enabled) noexcept {
    if(auto* s=runtime.load(std::memory_order_acquire)) {
        s->enabled.store(enabled,std::memory_order_release);
        if(!enabled) { s->render->Close(); }
    }
}
void Cleared(bool main) noexcept { if(auto* s=runtime.load(std::memory_order_acquire)) { s->Clear(main); } }
void ContextChanged() noexcept { if(auto* s=runtime.load(std::memory_order_acquire)) { s->Lost(); } }
}
bool Start() noexcept {
    const RenderLifecycleMutation mutation;
    if(runtime.load(std::memory_order_acquire)) { return false; }
    auto* s=new(std::nothrow) Runtime;
    if(!s) { return false; }
    if(!s->Configure()) { delete s; return false; }
    const auto base=s->native.Base(); IMAGE_DOS_HEADER dos{}; IMAGE_NT_HEADERS32 nt{};
    if(!SceneMatrixObservationCurrent()
        || !NativeCalls::Read(base,&dos,sizeof(dos)) || dos.e_lfanew<=0 || dos.e_lfanew>0x1000
        || !NativeCalls::Read(base+dos.e_lfanew,&nt,sizeof(nt)) || nt.OptionalHeader.SizeOfImage<0x16b0100
        || StartSceneContextObservation(reinterpret_cast<std::uint8_t*>(base),nt.OptionalHeader.SizeOfImage)!=ERROR_SUCCESS) {
        delete s; return false;
    }
    // The renderer is the sole matrix-IAT owner. All observers and the runtime
    // remain process-pinned, including after renderer Stop/context loss.
    runtime.store(s,std::memory_order_release);
    matrix_event.store(&MatrixChanged,std::memory_order_release);
    renderer_event.store(&RendererChanged,std::memory_order_release);
    depth_clear_event.store(&Cleared,std::memory_order_release);
    context_event.store(&ContextChanged,std::memory_order_release);
    furnishing_retire_service.store(&OwnerRetire,std::memory_order_release);
    furnishing_owner_service.store(&OwnerUpdate,std::memory_order_release);
    s->enabled.store(renderer_ready.load(std::memory_order_acquire),std::memory_order_release);
    return true;
}
}
