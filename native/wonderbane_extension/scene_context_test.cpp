// Production shared context ownership with controlled import/driver boundaries.
#include "scene_context.cpp"
#undef NDEBUG
#include <cassert>
#include <atomic>
#include <thread>
namespace wonderbane::extension {
namespace {
HGLRC observed_context = reinterpret_cast<HGLRC>(1);
HGLRC WINAPI ReadContext() { return observed_context; }
std::atomic<int> releases{0}, invalidations{0}, calls{0};
bool refuse_switch = false;
HANDLE entered = nullptr, resume = nullptr;
BOOL WINAPI SwitchContext(HDC, HGLRC context) {
    ++calls;
    if (entered) { SetEvent(entered); assert(WaitForSingleObject(resume, 5000) == WAIT_OBJECT_0); }
    if (refuse_switch) { return FALSE; }
    observed_context = context;
    return TRUE;
}
std::uint32_t imported_context = static_cast<std::uint32_t>(
    reinterpret_cast<std::uintptr_t>(&SwitchContext));
int installs = 0;
}
void ReleaseSelectedCueContext() noexcept { ++releases; }
void DiscardSkyScene() noexcept { ++invalidations; }
std::uint32_t* FindImportAddressSlot(std::uint8_t*, std::size_t, const char*, const char*) noexcept {
    return &imported_context;
}
DWORD ReplaceImportAddressSlot(std::uint32_t* slot, std::uint32_t expected,
                              std::uint32_t replacement) noexcept {
    if (*slot != expected) { return ERROR_BUSY; }
    *slot = replacement; ++installs; return ERROR_SUCCESS;
}
}
int main() {
    using namespace wonderbane::extension;
    current_context = &ReadContext;
    // No cue mapping/binding was started. Sky still receives context invalidation.
    assert(StartSceneContextObservation(nullptr, 0) == ERROR_SUCCESS);
    assert(StartSceneContextObservation(nullptr, 0) == ERROR_SUCCESS && installs == 1);
    const auto dispatch = reinterpret_cast<MakeCurrent>(imported_context);
    assert(dispatch(nullptr, reinterpret_cast<HGLRC>(2)));
    assert(dispatch(nullptr, reinterpret_cast<HGLRC>(1)));
    assert(releases == 2 && invalidations == 2 && calls == 2);
    refuse_switch = true;
    assert(!dispatch(nullptr, reinterpret_cast<HGLRC>(2)));
    assert(releases == 3 && invalidations == 3 && observed_context == reinterpret_cast<HGLRC>(1));
    refuse_switch = false;
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    resume = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HANDLE mutated = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    std::thread callback([&] { assert(dispatch(nullptr, nullptr)); });
    assert(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0);
    std::thread mutation([&] { RenderLifecycleMutation owner; SetEvent(mutated); });
    const auto deadline = GetTickCount64() + 5000;
    while (g_render_lifecycle.try_lock()) {
        g_render_lifecycle.unlock(); assert(GetTickCount64() < deadline); std::this_thread::yield();
    }
    assert(WaitForSingleObject(mutated, 50) == WAIT_TIMEOUT);
    SetEvent(resume); callback.join(); mutation.join();
    assert(WaitForSingleObject(mutated, 0) == WAIT_OBJECT_0);
    assert(StartSceneContextObservation(nullptr, 0) == ERROR_SUCCESS && installs == 1);
    for (HANDLE handle : {entered, resume, mutated}) { CloseHandle(handle); }
    return 0;
}
