#include "scene_context.h"
#include "import_hook.h"
#include "render_lifetime.h"
#include "selected_cue_runtime.h"
#include "sky_runtime.h"
namespace wonderbane::extension {
namespace {
using MakeCurrent = BOOL(WINAPI*)(HDC, HGLRC);
using CurrentContext = HGLRC(WINAPI*)();
std::uint32_t* context_slot = nullptr;
PVOID volatile original_context = nullptr;
CurrentContext current_context = &wglGetCurrentContext;
BOOL WINAPI SceneMakeCurrent(HDC dc, HGLRC context) noexcept {
    const RenderCallbackLease lease;
    const auto call = reinterpret_cast<MakeCurrent>(
        InterlockedCompareExchangePointer(&original_context, nullptr, nullptr));
    if (call == nullptr) { return FALSE; }
    if (context != current_context()) {
        // Release before unbinding while this thread still owns the old context.
        // A failed switch invalidates the scene too; it cannot resurrect authority.
        ReleaseSelectedCueContext();
        DiscardSkyScene();
    }
    return call(dc, context);
}
}
DWORD StartSceneContextObservation(std::uint8_t* image, std::size_t size) noexcept {
    const RenderLifecycleMutation mutation;
    auto* candidate = FindImportAddressSlot(image, size, "opengl32.dll", "wglMakeCurrent");
    if (candidate == nullptr) { return ERROR_PROC_NOT_FOUND; }
    const auto replacement = static_cast<std::uint32_t>(
        reinterpret_cast<std::uintptr_t>(&SceneMakeCurrent));
    if (context_slot != nullptr) {
        return candidate == context_slot && *context_slot == replacement
            ? ERROR_SUCCESS : ERROR_BUSY;
    }
    const auto original = *candidate;
    if (original == replacement) { return ERROR_BUSY; }
    InterlockedExchangePointer(&original_context, reinterpret_cast<void*>(original));
    const auto result = ReplaceImportAddressSlot(candidate, original, replacement);
    if (result == ERROR_SUCCESS) { context_slot = candidate; }
    return result;
}
}
