#include "cel_shading.h"
#include "import_hook.h"

#include <Windows.h>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kGlFlat = 0x1D00U;
constexpr unsigned int kGlPoints = 0x0000U;
constexpr unsigned int kGlLines = 0x0001U;
constexpr unsigned int kGlLineLoop = 0x0002U;
constexpr unsigned int kGlLineStrip = 0x0003U;
constexpr unsigned int kGlTriangles = 0x0004U;
constexpr unsigned int kGlTriangleStrip = 0x0005U;
constexpr unsigned int kGlTriangleFan = 0x0006U;
constexpr unsigned int kGlQuads = 0x0007U;
constexpr unsigned int kGlQuadStrip = 0x0008U;
constexpr unsigned int kGlPolygon = 0x0009U;
constexpr unsigned int kGlProjectionMatrix = 0x0BA7U;
constexpr unsigned int kGlTexture2D = 0x0DE1U;
constexpr unsigned int kGlLighting = 0x0B50U;
constexpr unsigned int kGlFog = 0x0B60U;
constexpr unsigned int kGlCullFace = 0x0B44U;
constexpr unsigned int kGlBlend = 0x0BE2U;
constexpr unsigned int kGlAlphaTest = 0x0BC0U;
constexpr unsigned int kGlFront = 0x0404U;
constexpr unsigned int kGlAllAttribBits = 0x000FFFFFU;
constexpr int kMaximumOutlinedElementCount = 8192;
constexpr float kOutlineScale = 1.018F;
constexpr float kOutlineRed = 0.025F;
constexpr float kOutlineGreen = 0.030F;
constexpr float kOutlineBlue = 0.040F;

using GlShadeModel = void(APIENTRY*)(unsigned int mode);
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
using GlPushAttrib = void(APIENTRY*)(unsigned int mask);
using GlPopAttrib = void(APIENTRY*)();
using GlPushMatrix = void(APIENTRY*)();
using GlPopMatrix = void(APIENTRY*)();
using GlScalef = void(APIENTRY*)(float x, float y, float z);
using GlEnable = void(APIENTRY*)(unsigned int capability);
using GlDisable = void(APIENTRY*)(unsigned int capability);
using GlCullFace = void(APIENTRY*)(unsigned int mode);
using GlColor4f = void(APIENTRY*)(float red, float green, float blue, float alpha);
using GlDepthMask = void(APIENTRY*)(unsigned char flag);

PVOID volatile g_original_shade_model = nullptr;
PVOID volatile g_original_begin = nullptr;
PVOID volatile g_original_call_list = nullptr;
PVOID volatile g_original_draw_arrays = nullptr;
PVOID volatile g_original_draw_elements = nullptr;
PVOID volatile g_get_floatv = nullptr;
PVOID volatile g_push_attrib = nullptr;
PVOID volatile g_pop_attrib = nullptr;
PVOID volatile g_push_matrix = nullptr;
PVOID volatile g_pop_matrix = nullptr;
PVOID volatile g_scalef = nullptr;
PVOID volatile g_enable = nullptr;
PVOID volatile g_disable = nullptr;
PVOID volatile g_cull_face = nullptr;
PVOID volatile g_color4f = nullptr;
PVOID volatile g_depth_mask = nullptr;
std::uint32_t* g_shade_model_slot = nullptr;
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

struct OutlineApi {
    GlGetFloatv get_floatv;
    GlPushAttrib push_attrib;
    GlPopAttrib pop_attrib;
    GlPushMatrix push_matrix;
    GlPopMatrix pop_matrix;
    GlScalef scalef;
    GlEnable enable;
    GlDisable disable;
    GlCullFace cull_face;
    GlColor4f color4f;
    GlDepthMask depth_mask;
};

bool LoadOutlineApi(OutlineApi* const api) noexcept {
    if (api == nullptr) {
        return false;
    }
    *api = {
        LoadFunction<GlGetFloatv>(&g_get_floatv),
        LoadFunction<GlPushAttrib>(&g_push_attrib),
        LoadFunction<GlPopAttrib>(&g_pop_attrib),
        LoadFunction<GlPushMatrix>(&g_push_matrix),
        LoadFunction<GlPopMatrix>(&g_pop_matrix),
        LoadFunction<GlScalef>(&g_scalef),
        LoadFunction<GlEnable>(&g_enable),
        LoadFunction<GlDisable>(&g_disable),
        LoadFunction<GlCullFace>(&g_cull_face),
        LoadFunction<GlColor4f>(&g_color4f),
        LoadFunction<GlDepthMask>(&g_depth_mask),
    };
    return api->get_floatv != nullptr
        && api->push_attrib != nullptr
        && api->pop_attrib != nullptr
        && api->push_matrix != nullptr
        && api->pop_matrix != nullptr
        && api->scalef != nullptr
        && api->enable != nullptr
        && api->disable != nullptr
        && api->cull_face != nullptr
        && api->color4f != nullptr
        && api->depth_mask != nullptr;
}

template <typename Draw>
void DrawWithSilhouette(const Draw& draw) noexcept {
    OutlineApi api{};
    std::array<float, 16U> projection{};
    if (!LoadOutlineApi(&api)) {
        draw();
        return;
    }
    api.get_floatv(kGlProjectionMatrix, projection.data());
    if (!IsPerspectiveProjectionMatrix(projection.data(), projection.size())) {
        draw();
        return;
    }

    api.push_attrib(kGlAllAttribBits);
    api.push_matrix();
    api.disable(kGlTexture2D);
    api.disable(kGlLighting);
    api.disable(kGlFog);
    api.disable(kGlBlend);
    api.disable(kGlAlphaTest);
    api.enable(kGlCullFace);
    api.cull_face(kGlFront);
    api.depth_mask(FALSE);
    api.color4f(kOutlineRed, kOutlineGreen, kOutlineBlue, 1.0F);
    api.scalef(kOutlineScale, kOutlineScale, kOutlineScale);
    draw();
    api.pop_matrix();
    api.pop_attrib();

    draw();
}

template <typename Value>
Value* ImageValue(
    std::uint8_t* const image,
    const std::size_t image_size,
    const std::uint32_t rva,
    const std::size_t count = 1U
) noexcept {
    if (
        image == nullptr
        || count == 0U
        || count > image_size / sizeof(Value)
        || rva > image_size
        || count * sizeof(Value) > image_size - rva
    ) {
        return nullptr;
    }
    return reinterpret_cast<Value*>(image + rva);
}

bool EqualAsciiInsensitive(
    const std::uint8_t* const image,
    const std::size_t image_size,
    const std::uint32_t rva,
    const char* const expected
) noexcept {
    if (image == nullptr || expected == nullptr || rva >= image_size) {
        return false;
    }
    std::size_t offset = rva;
    for (std::size_t index = 0U; ; ++index) {
        if (offset >= image_size) {
            return false;
        }
        const unsigned char actual = image[offset++];
        const unsigned char wanted = static_cast<unsigned char>(expected[index]);
        const auto fold = [](const unsigned char value) noexcept {
            return value >= static_cast<unsigned char>('A')
                    && value <= static_cast<unsigned char>('Z')
                ? static_cast<unsigned char>(value + ('a' - 'A'))
                : value;
        };
        if (fold(actual) != fold(wanted)) {
            return false;
        }
        if (actual == 0U) {
            return true;
        }
    }
}

void APIENTRY StrongShadeModel(const unsigned int) noexcept {
    const auto original = LoadFunction<GlShadeModel>(&g_original_shade_model);
    if (original != nullptr) {
        original(kGlFlat);
    }
}

void APIENTRY StrongBegin(const unsigned int mode) noexcept {
    const auto shade_model = LoadFunction<GlShadeModel>(&g_original_shade_model);
    if (shade_model != nullptr) {
        shade_model(kGlFlat);
    }
    const auto original = LoadFunction<GlBegin>(&g_original_begin);
    if (original != nullptr) {
        original(mode);
    }
}

void APIENTRY StrongCallList(const unsigned int list) noexcept {
    const auto original = LoadFunction<GlCallList>(&g_original_call_list);
    if (original != nullptr) {
        DrawWithSilhouette([original, list]() noexcept { original(list); });
    }
}

void APIENTRY StrongDrawArrays(
    const unsigned int mode,
    const int first,
    const int count
) noexcept {
    const auto original = LoadFunction<GlDrawArrays>(&g_original_draw_arrays);
    if (original != nullptr) {
        const auto draw = [original, mode, first, count]() noexcept {
            original(mode, first, count);
        };
        if (IsOutlinePrimitive(mode, count)) {
            DrawWithSilhouette(draw);
        } else {
            draw();
        }
    }
}

void APIENTRY StrongDrawElements(
    const unsigned int mode,
    const int count,
    const unsigned int type,
    const void* const indices
) noexcept {
    const auto original = LoadFunction<GlDrawElements>(&g_original_draw_elements);
    if (original != nullptr) {
        const auto draw = [original, mode, count, type, indices]() noexcept {
            original(mode, count, type, indices);
        };
        if (IsOutlinePrimitive(mode, count)) {
            DrawWithSilhouette(draw);
        } else {
            draw();
        }
    }
}

DWORD ReplaceImportSlot(
    std::uint32_t* const slot,
    const std::uint32_t expected,
    const std::uint32_t replacement
) noexcept {
    DWORD previous_protection = 0U;
    if (VirtualProtect(
            slot,
            sizeof(*slot),
            PAGE_READWRITE,
            &previous_protection
        ) == FALSE) {
        return GetLastError();
    }
    const LONG previous = InterlockedCompareExchange(
        reinterpret_cast<volatile LONG*>(slot),
        static_cast<LONG>(replacement),
        static_cast<LONG>(expected)
    );
    DWORD ignored_protection = 0U;
    const BOOL restore_result = VirtualProtect(
        slot,
        sizeof(*slot),
        previous_protection,
        &ignored_protection
    );
    if (previous != static_cast<LONG>(expected)) {
        return ERROR_INVALID_DATA;
    }
    if (restore_result == FALSE) {
        const DWORD restore_error = GetLastError();
        InterlockedCompareExchange(
            reinterpret_cast<volatile LONG*>(slot),
            static_cast<LONG>(expected),
            static_cast<LONG>(replacement)
        );
        VirtualProtect(
            slot,
            sizeof(*slot),
            previous_protection,
            &ignored_protection
        );
        return restore_error;
    }
    return ERROR_SUCCESS;
}

struct ImportHookPlan {
    const char* symbol_name;
    PVOID replacement;
    PVOID original;
    std::uint32_t* slot;
    PVOID volatile* original_storage;
    std::uint32_t** slot_storage;
};

struct HelperFunctionPlan {
    const char* symbol_name;
    PVOID volatile* storage;
    PVOID resolved;
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
    const DWORD result = ReplaceImportSlot(
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

bool IsPerspectiveProjectionMatrix(
    const float* const matrix,
    const std::size_t count
) noexcept {
    if (matrix == nullptr || count != 16U) {
        return false;
    }
    for (std::size_t index = 0U; index < count; ++index) {
        if (!std::isfinite(matrix[index])) {
            return false;
        }
    }
    return std::fabs(matrix[15]) < 0.001F
        && std::fabs(matrix[11]) > 0.25F;
}

bool IsOutlinePrimitive(const unsigned int mode, const int count) noexcept {
    if (count < 3 || count > kMaximumOutlinedElementCount) {
        return false;
    }
    switch (mode) {
        case kGlTriangles:
        case kGlTriangleStrip:
        case kGlTriangleFan:
        case kGlQuads:
        case kGlQuadStrip:
        case kGlPolygon:
            return true;
        case kGlPoints:
        case kGlLines:
        case kGlLineLoop:
        case kGlLineStrip:
        default:
            return false;
    }
}

std::size_t CelShadingHookCount(const CelShadingProfile profile) noexcept {
    switch (profile) {
        case CelShadingProfile::native:
            return 0U;
        case CelShadingProfile::flat:
            return 1U;
        case CelShadingProfile::outlined:
            return 5U;
        default:
            return 0U;
    }
}

DWORD SelectCelShadingProfile(
    const wchar_t* const configured_value,
    CelShadingProfile* const profile
) noexcept {
    if (profile == nullptr) {
        return ERROR_INVALID_PARAMETER;
    }
    if (configured_value == nullptr || configured_value[0] == L'\0') {
        *profile = CelShadingProfile::native;
        return ERROR_SUCCESS;
    }
    if (lstrcmpW(configured_value, L"native") == 0) {
        *profile = CelShadingProfile::native;
        return ERROR_SUCCESS;
    }
    if (lstrcmpW(configured_value, L"flat") == 0) {
        *profile = CelShadingProfile::flat;
        return ERROR_SUCCESS;
    }
    if (lstrcmpW(configured_value, L"outlined") == 0) {
        *profile = CelShadingProfile::outlined;
        return ERROR_SUCCESS;
    }
    return ERROR_INVALID_DATA;
}

std::uint32_t* FindImportAddressSlot(
    std::uint8_t* const image,
    const std::size_t image_size,
    const char* const library_name,
    const char* const symbol_name
) noexcept {
    if (
        image == nullptr
        || library_name == nullptr
        || symbol_name == nullptr
        || library_name[0] == '\0'
        || symbol_name[0] == '\0'
        || image_size < sizeof(IMAGE_DOS_HEADER)
    ) {
        return nullptr;
    }
    const auto* const dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(image);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) {
        return nullptr;
    }
    const std::size_t nt_offset = static_cast<std::size_t>(dos->e_lfanew);
    if (nt_offset > image_size || sizeof(IMAGE_NT_HEADERS32) > image_size - nt_offset) {
        return nullptr;
    }
    const auto* const nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(image + nt_offset);
    if (
        nt->Signature != IMAGE_NT_SIGNATURE
        || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386
        || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
        || nt->OptionalHeader.SizeOfImage != image_size
        || nt->OptionalHeader.NumberOfRvaAndSizes <= IMAGE_DIRECTORY_ENTRY_IMPORT
    ) {
        return nullptr;
    }
    const IMAGE_DATA_DIRECTORY imports = (
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT]
    );
    if (
        imports.VirtualAddress == 0U
        || imports.Size < sizeof(IMAGE_IMPORT_DESCRIPTOR)
        || imports.VirtualAddress > image_size
        || imports.Size > image_size - imports.VirtualAddress
    ) {
        return nullptr;
    }

    const std::size_t descriptor_count = imports.Size / sizeof(IMAGE_IMPORT_DESCRIPTOR);
    auto* const descriptors = ImageValue<IMAGE_IMPORT_DESCRIPTOR>(
        image,
        image_size,
        imports.VirtualAddress,
        descriptor_count
    );
    if (descriptors == nullptr) {
        return nullptr;
    }
    std::uint32_t* found = nullptr;
    bool terminated = false;
    for (std::size_t descriptor_index = 0U; descriptor_index < descriptor_count; ++descriptor_index) {
        const IMAGE_IMPORT_DESCRIPTOR& descriptor = descriptors[descriptor_index];
        if (
            descriptor.Name == 0U
            && descriptor.FirstThunk == 0U
            && descriptor.OriginalFirstThunk == 0U
            && descriptor.TimeDateStamp == 0U
            && descriptor.ForwarderChain == 0U
        ) {
            terminated = true;
            break;
        }
        if (!EqualAsciiInsensitive(image, image_size, descriptor.Name, library_name)) {
            continue;
        }
        const std::uint32_t names_rva = descriptor.OriginalFirstThunk != 0U
            ? descriptor.OriginalFirstThunk
            : descriptor.FirstThunk;
        if (
            names_rva == 0U
            || names_rva >= image_size
            || descriptor.FirstThunk == 0U
            || descriptor.FirstThunk >= image_size
        ) {
            return nullptr;
        }
        const std::size_t name_capacity = (image_size - names_rva) / sizeof(IMAGE_THUNK_DATA32);
        const std::size_t address_capacity = (
            image_size - descriptor.FirstThunk
        ) / sizeof(IMAGE_THUNK_DATA32);
        const std::size_t thunk_count = name_capacity < address_capacity
            ? name_capacity
            : address_capacity;
        auto* const names = ImageValue<IMAGE_THUNK_DATA32>(
            image,
            image_size,
            names_rva,
            thunk_count
        );
        auto* const addresses = ImageValue<IMAGE_THUNK_DATA32>(
            image,
            image_size,
            descriptor.FirstThunk,
            thunk_count
        );
        if (names == nullptr || addresses == nullptr) {
            return nullptr;
        }
        bool thunk_terminated = false;
        for (std::size_t thunk_index = 0U; thunk_index < thunk_count; ++thunk_index) {
            const std::uint32_t name_rva = names[thunk_index].u1.AddressOfData;
            if (name_rva == 0U) {
                thunk_terminated = true;
                break;
            }
            if ((name_rva & IMAGE_ORDINAL_FLAG32) != 0U) {
                continue;
            }
            constexpr std::uint32_t kImportHintSize = sizeof(std::uint16_t);
            if (
                name_rva > image_size
                || kImportHintSize > image_size - name_rva
                || !EqualAsciiInsensitive(
                    image,
                    image_size,
                    name_rva + kImportHintSize,
                    symbol_name
                )
            ) {
                continue;
            }
            auto* const candidate = reinterpret_cast<std::uint32_t*>(
                &addresses[thunk_index].u1.Function
            );
            if (found != nullptr) {
                return nullptr;
            }
            found = candidate;
        }
        if (!thunk_terminated) {
            return nullptr;
        }
    }
    return terminated ? found : nullptr;
}

DWORD StartStrongCelShading(const CelShadingProfile profile) noexcept {
    static_assert(sizeof(void*) == sizeof(std::uint32_t));
    if (profile != CelShadingProfile::flat && profile != CelShadingProfile::outlined) {
        return ERROR_INVALID_PARAMETER;
    }
    if (
        g_shade_model_slot != nullptr
        || g_begin_slot != nullptr
        || g_call_list_slot != nullptr
        || g_draw_arrays_slot != nullptr
        || g_draw_elements_slot != nullptr
        || g_original_shade_model != nullptr
        || g_original_begin != nullptr
        || g_original_call_list != nullptr
        || g_original_draw_arrays != nullptr
        || g_original_draw_elements != nullptr
        || g_get_floatv != nullptr
        || g_push_attrib != nullptr
        || g_pop_attrib != nullptr
        || g_push_matrix != nullptr
        || g_pop_matrix != nullptr
        || g_scalef != nullptr
        || g_enable != nullptr
        || g_disable != nullptr
        || g_cull_face != nullptr
        || g_color4f != nullptr
        || g_depth_mask != nullptr
    ) {
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
    if (
        nt->Signature != IMAGE_NT_SIGNATURE
        || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
    ) {
        return ERROR_BAD_EXE_FORMAT;
    }
    std::array<ImportHookPlan, 5U> plans{{
        {
            "glShadeModel",
            reinterpret_cast<PVOID>(&StrongShadeModel),
            nullptr,
            nullptr,
            &g_original_shade_model,
            &g_shade_model_slot,
        },
        {
            "glBegin",
            reinterpret_cast<PVOID>(&StrongBegin),
            nullptr,
            nullptr,
            &g_original_begin,
            &g_begin_slot,
        },
        {
            "glCallList",
            reinterpret_cast<PVOID>(&StrongCallList),
            nullptr,
            nullptr,
            &g_original_call_list,
            &g_call_list_slot,
        },
        {
            "glDrawArrays",
            reinterpret_cast<PVOID>(&StrongDrawArrays),
            nullptr,
            nullptr,
            &g_original_draw_arrays,
            &g_draw_arrays_slot,
        },
        {
            "glDrawElements",
            reinterpret_cast<PVOID>(&StrongDrawElements),
            nullptr,
            nullptr,
            &g_original_draw_elements,
            &g_draw_elements_slot,
        },
    }};
    // Flat shading only needs to reject later glShadeModel requests. Hooking glBegin as well
    // issued a redundant driver state call for every immediate-mode primitive and became a
    // measurable hot-path regression under llvmpipe.
    const std::size_t plan_count = CelShadingHookCount(profile);
    auto* const image = reinterpret_cast<std::uint8_t*>(executable);
    for (std::size_t index = 0U; index < plan_count; ++index) {
        ImportHookPlan& plan = plans[index];
        plan.slot = FindImportAddressSlot(
            image,
            nt->OptionalHeader.SizeOfImage,
            "OPENGL32.dll",
            plan.symbol_name
        );
        plan.original = reinterpret_cast<PVOID>(GetProcAddress(opengl, plan.symbol_name));
        if (plan.slot == nullptr || plan.original == nullptr) {
            return ERROR_PROC_NOT_FOUND;
        }
        const std::uintptr_t original_address = reinterpret_cast<std::uintptr_t>(plan.original);
        const std::uintptr_t replacement_address = reinterpret_cast<std::uintptr_t>(
            plan.replacement
        );
        if (
            original_address > UINT32_MAX
            || replacement_address > UINT32_MAX
            || *plan.slot != static_cast<std::uint32_t>(original_address)
        ) {
            return ERROR_INVALID_ADDRESS;
        }
    }
    for (std::size_t left = 0U; left < plan_count; ++left) {
        for (std::size_t right = left + 1U; right < plan_count; ++right) {
            if (plans[left].slot == plans[right].slot) {
                return ERROR_INVALID_DATA;
            }
        }
    }

    std::array<HelperFunctionPlan, 11U> helpers{{
        {"glGetFloatv", &g_get_floatv, nullptr},
        {"glPushAttrib", &g_push_attrib, nullptr},
        {"glPopAttrib", &g_pop_attrib, nullptr},
        {"glPushMatrix", &g_push_matrix, nullptr},
        {"glPopMatrix", &g_pop_matrix, nullptr},
        {"glScalef", &g_scalef, nullptr},
        {"glEnable", &g_enable, nullptr},
        {"glDisable", &g_disable, nullptr},
        {"glCullFace", &g_cull_face, nullptr},
        {"glColor4f", &g_color4f, nullptr},
        {"glDepthMask", &g_depth_mask, nullptr},
    }};
    if (profile == CelShadingProfile::outlined) {
        for (HelperFunctionPlan& helper : helpers) {
            helper.resolved = reinterpret_cast<PVOID>(GetProcAddress(opengl, helper.symbol_name));
            if (helper.resolved == nullptr) {
                return ERROR_PROC_NOT_FOUND;
            }
        }
        for (HelperFunctionPlan& helper : helpers) {
            InterlockedExchangePointer(helper.storage, helper.resolved);
        }
    }
    for (std::size_t index = 0U; index < plan_count; ++index) {
        ImportHookPlan& plan = plans[index];
        InterlockedExchangePointer(plan.original_storage, plan.original);
        const DWORD result = ReplaceImportSlot(
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
            StopStrongCelShading();
            return result;
        }
        *plan.slot_storage = plan.slot;
    }
    return ERROR_SUCCESS;
}

void StopStrongCelShading() noexcept {
    bool restored = true;
    if (!RestoreHook(
            &g_draw_elements_slot,
            &g_original_draw_elements,
            reinterpret_cast<PVOID>(&StrongDrawElements)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_draw_arrays_slot,
            &g_original_draw_arrays,
            reinterpret_cast<PVOID>(&StrongDrawArrays)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_call_list_slot,
            &g_original_call_list,
            reinterpret_cast<PVOID>(&StrongCallList)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_begin_slot,
            &g_original_begin,
            reinterpret_cast<PVOID>(&StrongBegin)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_shade_model_slot,
            &g_original_shade_model,
            reinterpret_cast<PVOID>(&StrongShadeModel)
        )) {
        restored = false;
    }
    if (restored) {
        InterlockedExchangePointer(&g_depth_mask, nullptr);
        InterlockedExchangePointer(&g_color4f, nullptr);
        InterlockedExchangePointer(&g_cull_face, nullptr);
        InterlockedExchangePointer(&g_disable, nullptr);
        InterlockedExchangePointer(&g_enable, nullptr);
        InterlockedExchangePointer(&g_scalef, nullptr);
        InterlockedExchangePointer(&g_pop_matrix, nullptr);
        InterlockedExchangePointer(&g_push_matrix, nullptr);
        InterlockedExchangePointer(&g_pop_attrib, nullptr);
        InterlockedExchangePointer(&g_push_attrib, nullptr);
        InterlockedExchangePointer(&g_get_floatv, nullptr);
    }
}

}  // namespace wonderbane::extension
