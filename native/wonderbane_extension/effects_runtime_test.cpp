// Exercise the production channel and synchronized cleanup, without a game.
#include "effects_runtime.cpp"
#include <cstdio>
#include <thread>
#include <atomic>
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return true; }
bool RenderEffectsGeometry(const effects::Config&,const effects::Geometry&,const GraphicsCameraState&) noexcept { return false; }
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
    std::atomic<bool> running{true};
    std::thread draw([&]() { while (running.load()) DrawEffects(nullptr); });
    StopEffects(); running=false; draw.join();
    check(!g_control && !g_mapping && !g_system.stats.particles,"concurrent shutdown releases mapping and history");
    StopEffects(); check(StartEffects(identity)==ERROR_SUCCESS,"restart creates fresh disabled mapping");
    check(!g_control->config.flags && !g_control->desired,"restart starts disabled"); StopEffects();
    return failures ? 1:0;
}
