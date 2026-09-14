// Exercise the production channel and synchronized cleanup, without a game.
#include "effects.h"
#include <windows.h>
#include <gl/GL.h>
namespace {
int resolve_calls=0, render_calls=0;
HGLRC test_context=reinterpret_cast<HGLRC>(0x1234U);
HGLRC WINAPI TestCurrentContext() { return test_context; }
}
namespace wonderbane::extension::effects {
Attachment TestResolve(Reader,void*,std::uint32_t,std::uint32_t) noexcept {
    ++resolve_calls;
    return {0x10000,1,2,0x20000,0x30000,0x40000,3,4,{100,5,-100},true};
}
}
// Exercise the production runtime; only external attachment/context/render endpoints are faked.
#define wglGetCurrentContext TestCurrentContext
#define Resolve TestResolve
#include "effects_runtime.cpp"
#undef Resolve
#undef wglGetCurrentContext
#include <cstdio>
#include <thread>
#include <atomic>
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return true; }
bool RenderEffectsGeometry(const effects::Config&,const effects::Geometry&,const GraphicsCameraState&) noexcept { ++render_calls; return true; }
}
using namespace wonderbane::extension;
int main() {
    int failures=0;
    const auto check=[&](bool ok,const char* label) { if (!ok) { std::fprintf(stderr,"%s\n",label); ++failures; } };
    const ProcessIdentity identity{GetCurrentProcessId(),123456789U};
    check(StartEffects({identity.process_id,0})==ERROR_NOT_SUPPORTED,"invalid process identity rejected");
    check(StartEffects(identity)==ERROR_SUCCESS,"start native effects mapping");
    check(StartEffects(identity)==ERROR_ALREADY_INITIALIZED,"duplicate start rejected");
    check(g_control && g_control->pid==identity.process_id && g_control->config.flags==0,"starts disabled");
    g_control->config.flags=7; InterlockedExchange(&g_control->desired,2);
    DrawEffects(nullptr);
    check(g_control->applied==2 && g_config.flags==7,"valid settings acknowledged");
    check(!g_control->stats.particles && !g_control->stats.samples,"no camera cannot retain effects");
    g_control->config.flags=16; InterlockedExchange(&g_control->desired,4);
    DrawEffects(nullptr);
    check(g_control->applied==2 && g_control->error==ERROR_INVALID_DATA && !g_config.flags,"invalid settings fail closed");
    g_control->config={}; g_control->config.flags=7; InterlockedExchange(&g_control->desired,5);
    DrawEffects(nullptr);
    check(!g_config.flags,"torn settings fail closed");
    InterlockedExchange(&g_control->desired,6); DrawEffects(nullptr);
    check(g_control->applied==6 && !g_control->error,"valid settings recover");
    ++g_control->creation; InterlockedExchange(&g_control->desired,8); DrawEffects(nullptr);
    check(!g_config.flags && g_control->error==ERROR_INVALID_DATA,"wrong identity rejected");
    // A verified safe scene renders first; loss of authority clears real history.
    --g_control->creation;
    GraphicsCameraState camera{};
    camera.view_matrix[0]=1; camera.up[1]=1; camera.forward[2]=-1;
    camera.position[0]=100; camera.position[1]=5; camera.position[2]=-90;
    g_control->config={}; InterlockedExchange(&g_control->desired,10); DrawEffects(&camera,true);
    check(!g_suppressed && g_control->presentation==kDisabled,"acknowledged disable clears latch");
    g_control->config.flags=7; g_control->config.rate=0; g_control->config.burst=1;
    InterlockedExchange(&g_control->desired,12); DrawEffects(&camera,true);
    check(render_calls>0 && g_control->stats.particles>0,"safe authority permits production simulation/draw");
    const int previous_render=render_calls, previous_resolve=resolve_calls;
    const auto previous_suppressed=g_control->suppressed_frames;
    ++g_control->config.burst; InterlockedExchange(&g_control->desired,14);
    DrawEffects(&camera); // Omitted authority is unsafe even with valid camera/context/attachment.
    check(g_config.flags==7 && g_control->presentation==kSuppressed && g_suppressed,
        "requested enabled remains distinct from default-deny suppression");
    check(!g_control->stats.particles && !g_control->stats.samples && !g_geometry.count,
        "unsafe frame clears existing particles, trail and geometry");
    check(render_calls==previous_render && resolve_calls==previous_resolve,
        "unsafe frame performs no attachment reads or draw callbacks");
    for(int i=0;i<20;++i) DrawEffects(&camera,(i%2)==0);
    check(g_control->presentation==kSuppressed && render_calls==previous_render,
        "alternating authority cannot flicker or release suppression");
    check(g_control->suppressed_frames==previous_suppressed+21 && g_control->safety_version==1,
        "suppression is explicitly observable");
    test_context=reinterpret_cast<HGLRC>(0x5678U); DrawEffects(&camera,true);
    check(g_suppressed,"context replacement does not bypass explicit retry");
    const auto canceled_token=g_config.burst;
    g_control->config.flags=0; InterlockedExchange(&g_control->desired,16); DrawEffects(&camera,true);
    check(!g_suppressed && g_control->presentation==kDisabled,"disable clears suppression");
    g_control->config.flags=7; InterlockedExchange(&g_control->desired,18); DrawEffects(&camera,true);
    check(!g_control->stats.particles && g_config.burst==canceled_token && render_calls==previous_render,
        "reenable cannot replay canceled burst or old geometry");
    ++g_control->config.burst; InterlockedExchange(&g_control->desired,20); DrawEffects(&camera,true);
    check(g_control->stats.particles>0 && render_calls>previous_render,"fresh explicit safe burst works");
    g_control->suppressed_frames=UINT32_MAX; DrawEffects(&camera,false);
    check(g_control->suppressed_frames==UINT32_MAX,"suppression counter saturates");
    std::puts("conservative effects fallback executed: suppression, cleanup, burst cancellation, latch, retry");
    std::atomic<bool> running{true};
    std::thread draw([&]() { while (running.load()) DrawEffects(nullptr); });
    StopEffects(); running=false; draw.join();
    check(!g_control && !g_mapping && !g_system.stats.particles,"concurrent shutdown releases mapping and history");
    StopEffects(); check(StartEffects(identity)==ERROR_SUCCESS,"restart creates fresh disabled mapping");
    check(!g_control->config.flags && !g_control->desired,"restart starts disabled"); StopEffects();
    return failures ? 1:0;
}
