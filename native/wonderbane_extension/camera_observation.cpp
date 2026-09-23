#include "camera_observation.h"

#include "graphics_status.h"
#include "import_hook.h"

#include <Windows.h>

#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kGlTriangles = 0x0004U;
constexpr unsigned int kGlTriangleStrip = 0x0005U;
constexpr unsigned int kGlTriangleFan = 0x0006U;
constexpr unsigned int kGlQuads = 0x0007U;
constexpr unsigned int kGlQuadStrip = 0x0008U;
constexpr unsigned int kGlPolygon = 0x0009U;
constexpr unsigned int kGlModelViewMatrix = 0x0BA6U;
constexpr unsigned int kGlProjectionMatrix = 0x0BA7U;
constexpr unsigned int kGlViewport = 0x0BA2U;
constexpr unsigned int kGlListIndex = 0x0B33U;
constexpr unsigned int kGlModelViewStackDepth = 0x0BA3U;
constexpr unsigned int kGlDepthWriteMask = 0x0B72U;

using GlBegin = void(APIENTRY*)(unsigned int mode);
using GlCallList = void(APIENTRY*)(unsigned int list);
using GlDrawArrays = void(APIENTRY*)(unsigned int mode, int first, int count);
using GlDrawElements = void(APIENTRY*)(
    unsigned int mode,
    int count,
    unsigned int type,
    const void* indices
);
using GlGetFloatv = void(APIENTRY*)(unsigned int name, float* values);
using GlGetBooleanv = void(APIENTRY*)(unsigned int name, unsigned char* values);
using GlGetIntegerv = void(APIENTRY*)(unsigned int name, int* values);

PVOID volatile g_original_begin = nullptr;
PVOID volatile g_original_call_list = nullptr;
PVOID volatile g_original_draw_arrays = nullptr;
PVOID volatile g_original_draw_elements = nullptr;
PVOID volatile g_get_floatv = nullptr;
PVOID volatile g_get_booleanv = nullptr;
PVOID volatile g_get_integerv = nullptr;
std::uint32_t* g_begin_slot = nullptr;
std::uint32_t* g_call_list_slot = nullptr;
std::uint32_t* g_draw_arrays_slot = nullptr;
std::uint32_t* g_draw_elements_slot = nullptr;

template <typename Function>
Function LoadFunction(PVOID volatile* const storage) noexcept {
    return reinterpret_cast<Function>(InterlockedCompareExchangePointer(
        storage,
        nullptr,
        nullptr
    ));
}

bool IsFilledPrimitiveMode(const unsigned int mode) noexcept {
    return mode == kGlTriangles
        || mode == kGlTriangleStrip
        || mode == kGlTriangleFan
        || mode == kGlQuads
        || mode == kGlQuadStrip
        || mode == kGlPolygon;
}

void ObservePassiveCameraState() noexcept {
    if (!NeedsGraphicsCameraStateObservation()) {
        return;
    }
    const auto get_floatv = LoadFunction<GlGetFloatv>(&g_get_floatv);
    const auto get_booleanv = LoadFunction<GlGetBooleanv>(&g_get_booleanv);
    const auto get_integerv = LoadFunction<GlGetIntegerv>(&g_get_integerv);
    if (get_floatv == nullptr || get_booleanv == nullptr || get_integerv == nullptr) {
        return;
    }
    int display_list_index = 0;
    int model_view_stack_depth = 0;
    get_integerv(kGlListIndex, &display_list_index);
    get_integerv(kGlModelViewStackDepth, &model_view_stack_depth);
    if (display_list_index != 0 || model_view_stack_depth != 1) {
        return;
    }
    unsigned char depth_writes = FALSE;
    get_booleanv(kGlDepthWriteMask, &depth_writes);
    if (depth_writes == FALSE) {
        return;
    }
    std::array<float, 16U> projection{};
    std::array<float, 16U> view{};
    std::array<int, 4U> viewport{};
    get_floatv(kGlProjectionMatrix, projection.data());
    get_floatv(kGlModelViewMatrix, view.data());
    get_integerv(kGlViewport, viewport.data());
    ObserveGraphicsCameraState(
        view.data(),
        view.size(),
        projection.data(),
        projection.size(),
        viewport.data(),
        viewport.size(),
        model_view_stack_depth
    );
}

void APIENTRY PassiveBegin(const unsigned int mode) noexcept {
    if (IsFilledPrimitiveMode(mode)) {
        ObservePassiveCameraState();
    }
    const auto original = LoadFunction<GlBegin>(&g_original_begin);
    if (original != nullptr) {
        original(mode);
    }
}

void APIENTRY PassiveCallList(const unsigned int list) noexcept {
    ObservePassiveCameraState();
    const auto original = LoadFunction<GlCallList>(&g_original_call_list);
    if (original != nullptr) {
        original(list);
    }
}

void APIENTRY PassiveDrawArrays(
    const unsigned int mode,
    const int first,
    const int count
) noexcept {
    if (count >= 3 && IsFilledPrimitiveMode(mode)) {
        ObservePassiveCameraState();
    }
    const auto original = LoadFunction<GlDrawArrays>(&g_original_draw_arrays);
    if (original != nullptr) {
        original(mode, first, count);
    }
}

void APIENTRY PassiveDrawElements(
    const unsigned int mode,
    const int count,
    const unsigned int type,
    const void* const indices
) noexcept {
    if (count >= 3 && IsFilledPrimitiveMode(mode)) {
        ObservePassiveCameraState();
    }
    const auto original = LoadFunction<GlDrawElements>(&g_original_draw_elements);
    if (original != nullptr) {
        original(mode, count, type, indices);
    }
}

struct ImportPlan {
    const char* symbol_name;
    PVOID replacement;
    PVOID original;
    std::uint32_t* slot;
    PVOID volatile* original_storage;
    std::uint32_t** slot_storage;
};

bool RestoreHook(
    std::uint32_t** const slot_storage,
    PVOID volatile* const original_storage,
    PVOID const replacement
) noexcept {
    std::uint32_t* const slot = *slot_storage;
    PVOID const original = LoadFunction<PVOID>(original_storage);
    if (slot == nullptr && original == nullptr) {
        return true;
    }
    if (slot == nullptr || original == nullptr) {
        return false;
    }
    const std::uintptr_t original_address = reinterpret_cast<std::uintptr_t>(original);
    const std::uintptr_t replacement_address = reinterpret_cast<std::uintptr_t>(replacement);
    if (original_address > UINT32_MAX || replacement_address > UINT32_MAX) {
        return false;
    }
    const DWORD result = ReplaceImportAddressSlot(
        slot,
        static_cast<std::uint32_t>(replacement_address),
        static_cast<std::uint32_t>(original_address)
    );
    if (result != ERROR_SUCCESS) {
        return false;
    }
    *slot_storage = nullptr;
    InterlockedExchangePointer(original_storage, nullptr);
    return true;
}

}  // namespace

DWORD StartPassiveCameraObservation() noexcept {
    static_assert(sizeof(void*) == sizeof(std::uint32_t));
    if (g_begin_slot != nullptr || g_call_list_slot != nullptr
        || g_draw_arrays_slot != nullptr || g_draw_elements_slot != nullptr
        || g_original_begin != nullptr || g_original_call_list != nullptr
        || g_original_draw_arrays != nullptr || g_original_draw_elements != nullptr
        || g_get_floatv != nullptr || g_get_booleanv != nullptr
        || g_get_integerv != nullptr) {
        return ERROR_ALREADY_INITIALIZED;
    }
    const HMODULE executable = GetModuleHandleW(nullptr);
    const HMODULE opengl = GetModuleHandleW(L"OPENGL32.dll");
    if (executable == nullptr || opengl == nullptr) {
        return ERROR_MOD_NOT_FOUND;
    }
    const auto* const dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(executable);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) {
        return ERROR_BAD_EXE_FORMAT;
    }
    const auto* const nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(
        reinterpret_cast<const std::uint8_t*>(executable) + dos->e_lfanew
    );
    if (nt->Signature != IMAGE_NT_SIGNATURE
        || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC) {
        return ERROR_BAD_EXE_FORMAT;
    }
    std::array<ImportPlan, 4U> plans{{
        {"glBegin", reinterpret_cast<PVOID>(&PassiveBegin), nullptr, nullptr,
         &g_original_begin, &g_begin_slot},
        {"glCallList", reinterpret_cast<PVOID>(&PassiveCallList), nullptr, nullptr,
         &g_original_call_list, &g_call_list_slot},
        {"glDrawArrays", reinterpret_cast<PVOID>(&PassiveDrawArrays), nullptr, nullptr,
         &g_original_draw_arrays, &g_draw_arrays_slot},
        {"glDrawElements", reinterpret_cast<PVOID>(&PassiveDrawElements), nullptr, nullptr,
         &g_original_draw_elements, &g_draw_elements_slot},
    }};
    auto* const image = reinterpret_cast<std::uint8_t*>(executable);
    for (ImportPlan& plan : plans) {
        plan.slot = FindImportAddressSlot(
            image, nt->OptionalHeader.SizeOfImage, "OPENGL32.dll", plan.symbol_name
        );
        plan.original = reinterpret_cast<PVOID>(
            GetProcAddress(opengl, plan.symbol_name)
        );
        const std::uintptr_t original_address = reinterpret_cast<std::uintptr_t>(
            plan.original
        );
        const std::uintptr_t replacement_address = reinterpret_cast<std::uintptr_t>(
            plan.replacement
        );
        if (plan.slot == nullptr || plan.original == nullptr
            || original_address > UINT32_MAX || replacement_address > UINT32_MAX
            || *plan.slot != static_cast<std::uint32_t>(original_address)) {
            return ERROR_REVISION_MISMATCH;
        }
    }
    for (std::size_t left = 0U; left < plans.size(); ++left) {
        for (std::size_t right = left + 1U; right < plans.size(); ++right) {
            if (plans[left].slot == plans[right].slot) {
                return ERROR_INVALID_DATA;
            }
        }
    }
    struct HelperPlan {
        const char* symbol_name;
        PVOID volatile* storage;
        PVOID resolved;
    };
    std::array<HelperPlan, 3U> helpers{{
        {"glGetFloatv", &g_get_floatv, nullptr},
        {"glGetBooleanv", &g_get_booleanv, nullptr},
        {"glGetIntegerv", &g_get_integerv, nullptr},
    }};
    for (HelperPlan& helper : helpers) {
        helper.resolved = reinterpret_cast<PVOID>(
            GetProcAddress(opengl, helper.symbol_name)
        );
        if (helper.resolved == nullptr) {
            return ERROR_PROC_NOT_FOUND;
        }
    }
    for (HelperPlan& helper : helpers) {
        InterlockedExchangePointer(helper.storage, helper.resolved);
    }
    for (ImportPlan& plan : plans) {
        InterlockedExchangePointer(plan.original_storage, plan.original);
        const DWORD result = ReplaceImportAddressSlot(
            plan.slot,
            static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(plan.original)),
            static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(plan.replacement))
        );
        if (result != ERROR_SUCCESS) {
            const auto replacement_address = static_cast<std::uint32_t>(
                reinterpret_cast<std::uintptr_t>(plan.replacement)
            );
            if (*plan.slot == replacement_address) {
                *plan.slot_storage = plan.slot;
            } else {
                InterlockedExchangePointer(plan.original_storage, nullptr);
            }
            StopPassiveCameraObservation();
            return result;
        }
        *plan.slot_storage = plan.slot;
    }
    return ERROR_SUCCESS;
}

void StopPassiveCameraObservation() noexcept {
    bool restored = RestoreHook(
        &g_draw_elements_slot, &g_original_draw_elements,
        reinterpret_cast<PVOID>(&PassiveDrawElements)
    );
    restored = RestoreHook(
        &g_draw_arrays_slot, &g_original_draw_arrays,
        reinterpret_cast<PVOID>(&PassiveDrawArrays)
    ) && restored;
    restored = RestoreHook(
        &g_call_list_slot, &g_original_call_list,
        reinterpret_cast<PVOID>(&PassiveCallList)
    ) && restored;
    restored = RestoreHook(
        &g_begin_slot, &g_original_begin, reinterpret_cast<PVOID>(&PassiveBegin)
    ) && restored;
    if (restored) {
        InterlockedExchangePointer(&g_get_integerv, nullptr);
        InterlockedExchangePointer(&g_get_booleanv, nullptr);
        InterlockedExchangePointer(&g_get_floatv, nullptr);
    }
}

}  // namespace wonderbane::extension
