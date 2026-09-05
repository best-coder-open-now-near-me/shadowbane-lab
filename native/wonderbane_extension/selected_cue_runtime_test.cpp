#include "selected_cue_runtime.cpp"
#undef NDEBUG
#include <cassert>
#include <atomic>
#include <thread>

namespace wonderbane::extension::cue {
std::atomic<int> begins{0},before{0},after{0},composites{0},releases{0},discards{0};
thread_local bool resources=false;
thread_local int local_releases=0;
bool begin_ok=true,before_ok=true,after_ok=true;
bool BeginMask() noexcept {++begins;resources=begin_ok;return begin_ok;}
bool BeforeOwnedDraw() noexcept {++before;return before_ok;}
bool AfterOwnedDraw() noexcept {++after;return after_ok;}
bool CompositeMask(const Settings&,const Direction&) noexcept {++composites;return true;}
void DiscardMask() noexcept {++discards;}
void ReleaseMask() noexcept {++releases;if(resources){++local_releases;resources=false;}}
}
namespace {
int draws=0;
bool clear_during_draw=false;
HANDLE draw_entered=nullptr,draw_resume=nullptr;
void __fastcall Draw(void*,void*) noexcept {
    ++draws;
    if(draw_entered){SetEvent(draw_entered);assert(WaitForSingleObject(draw_resume,5000)==WAIT_OBJECT_0);}
    if(clear_during_draw)*reinterpret_cast<std::uint32_t*>(wonderbane::extension::base+23735716U)=0;
}
}
int main(){
    using namespace wonderbane::extension;
    auto* memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1900000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    assert(memory);base=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(memory));
    const auto put=[&](unsigned address,std::uint32_t value){std::memcpy(reinterpret_cast<void*>(address),&value,4);};
    const auto actor=base+0x1000,component=base+0x4000,location=base+0x5000,zone=base+0x6000,render=base+0x7000,wrapper=base+0x8000;
    put(base+23735704,actor);put(base+23735716,actor);put(actor,base+0x114165c);
    put(base+0x114165c+88,base+41936);put(actor+120,1);put(actor+124,2);
    put(actor+1200,component);put(component,location);put(actor+3392,zone);
    put(zone+120,3);put(zone+124,4);put(actor+0xc0,render);put(wrapper+0x1c,render);
    const float position[]{300,4,-300};std::memcpy(reinterpret_cast<void*>(location+32),position,12);
    Control block{};block.pid=GetCurrentProcessId();block.settings.enabled=1;control=&block;
    InterlockedExchange(&running,1);InterlockedExchangePointer(&original,reinterpret_cast<void*>(&Draw));
    GraphicsCameraState camera{};camera.position[0]=300;camera.position[1]=4;
    camera.forward[2]=-1;camera.viewport[2]=800;camera.viewport[3]=600;
    for(int n=0;n<4;++n)camera.view_matrix[n*5]=1;
    camera.view_matrix[12]=-300;camera.view_matrix[13]=-4;
    camera.projection_matrix[0]=1;camera.projection_matrix[5]=1;
    camera.projection_matrix[10]=-1;camera.projection_matrix[11]=-1;camera.projection_matrix[14]=-0.2F;
    assert(Selected().valid);BeginSelectedCueScene(&camera);assert(scene && render_count==1);
    OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);
    assert(draws==1 && cue::before==1 && cue::after==1);
    FinishSelectedCueScene(&camera);assert(cue::composites==1 && !scene);EndSelectedCueFrame();
    // A different object's render wrapper cannot acquire the selected mask.
    BeginSelectedCueScene(&camera);put(wrapper+0x1c,render+0x100);
    OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);assert(draws==2 && cue::before==1);
    // Selection loss during the original call discards the candidate.
    put(wrapper+0x1c,render);clear_during_draw=true;
    OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);assert(draws==3 && cue::after==1);
    FinishSelectedCueScene(&camera);assert(cue::composites==1 && !scene);
    clear_during_draw=false;put(base+23735716,actor);put(actor+124,99);
    BeginSelectedCueScene(&camera);assert(attachment.uuid==99);
    EndSelectedCueFrame();assert(!scene && render_count==0);
    // Mask failures must survive a successful indicator-only composite.
    for(int failure=0;failure<3;++failure){
        cue::begin_ok=failure!=0;cue::before_ok=failure!=1;cue::after_ok=failure!=2;
        BeginSelectedCueScene(&camera);OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);
        FinishSelectedCueScene(&camera);assert(block.render_error==1);EndSelectedCueFrame();
    }
    cue::begin_ok=cue::before_ok=cue::after_ok=true;
    BeginSelectedCueScene(&camera);
    for(int n=0;n<129;++n)OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);
    FinishSelectedCueScene(&camera);assert(block.render_error==1);EndSelectedCueFrame();
    BeginSelectedCueScene(&camera);OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);
    FinishSelectedCueScene(&camera);assert(block.render_error==0);EndSelectedCueFrame();
    block.settings.enabled=0;BeginSelectedCueScene(&camera);assert(!scene && cue::releases>0);
    block.settings.enabled=2;assert(!Poll());assert(block.error==ERROR_INVALID_DATA);
    block.settings.enabled=1;block.sequence=3;assert(!Poll());block.sequence=4;
    // Out-of-range render children are rejected before dereferencing.
    attachment=Selected();put(render+0x3c,0xfffffff0);put(render+0x40,0xfffffff4);assert(!CollectRenders());
    control=nullptr;InterlockedExchange(&running,0);original=nullptr;base=0;
    assert(StartSelectedCue(memory,0x1900000,"unknown")==ERROR_REVISION_MISMATCH);
    assert(control && control->binding==0);StopSelectedCue();assert(!control && !mapping);
    // Stop drains an admitted wrapper. Its worker cannot release render-thread
    // resources; a later generation releases those before reuse on that thread.
    put(render+0x3c,0);put(render+0x40,0);
    assert(StartSelectedCue(memory,0x1900000,"unknown")==ERROR_REVISION_MISMATCH);
    control->settings.enabled=1;InterlockedExchange(&running,1);
    InterlockedExchangePointer(&original,reinterpret_cast<void*>(&Draw));
    draw_entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    draw_resume=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE stop_started=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE stopped=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE restart=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::uint32_t retained_hook=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&CueMakeCurrent));
    context_slot=&retained_hook;
    std::thread render_thread([&]{
        BeginSelectedCueScene(&camera);assert(cue::resources);
        const int released=cue::local_releases;
        OwnedRender(reinterpret_cast<void*>(wrapper),nullptr);
        assert(WaitForSingleObject(restart,5000)==WAIT_OBJECT_0);
        assert(cue::resources && cue::local_releases==released);
        BeginSelectedCueScene(&camera);
        assert(cue::resources && cue::local_releases==released+1);
        ReleaseSelectedCueContext();assert(!cue::resources);
    });
    assert(WaitForSingleObject(draw_entered,5000)==WAIT_OBJECT_0);
    std::thread stopper([&]{SetEvent(stop_started);StopSelectedCue();SetEvent(stopped);});
    assert(WaitForSingleObject(stop_started,5000)==WAIT_OBJECT_0);
    const auto deadline=GetTickCount64()+5000;
    while(g_render_lifecycle.try_lock()){
        g_render_lifecycle.unlock();assert(GetTickCount64()<deadline);std::this_thread::yield();
    }
    assert(WaitForSingleObject(stopped,50)==WAIT_TIMEOUT);
    // A concurrent restart must serialize behind the draining mutation.
    HANDLE restart_done=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    std::thread restarter([&]{
        assert(StartSelectedCue(memory,0x1900000,"unknown")==ERROR_REVISION_MISMATCH);
        SetEvent(restart_done);
    });
    assert(WaitForSingleObject(restart_done,50)==WAIT_TIMEOUT);
    SetEvent(draw_resume);assert(WaitForSingleObject(stopped,5000)==WAIT_OBJECT_0);stopper.join();
    assert(WaitForSingleObject(restart_done,5000)==WAIT_OBJECT_0);restarter.join();
    assert(context_slot==&retained_hook && retained_hook==static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&CueMakeCurrent)));
    control->settings.enabled=1;InterlockedExchange(&running,1);
    SetEvent(restart);render_thread.join();
    CloseHandle(draw_entered);draw_entered=nullptr;context_slot=nullptr;StopSelectedCue();
    for(HANDLE event:{draw_resume,stop_started,stopped,restart,restart_done})CloseHandle(event);
    VirtualFree(memory,0,MEM_RELEASE);
}

namespace wonderbane::extension { void DiscardSkyScene() noexcept {} }
