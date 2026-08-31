#include "cel_shading.h"

#include <Windows.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kGlFlat = 0x1D00U;
constexpr unsigned int kGlFrontAndBack = 0x0408U;
constexpr unsigned int kGlLine = 0x1B01U;

using GlShadeModel = void(APIENTRY*)(unsigned int mode);
using GlBegin = void(APIENTRY*)(unsigned int mode);
using GlDrawArrays = void(APIENTRY*)(unsigned int mode, int first, int count);
using GlDrawElements = void(APIENTRY*)(
    unsigned int mode,
    int count,
    unsigned int type,
    const void* indices
);
using GlPolygonMode = void(APIENTRY*)(unsigned int face, unsigned int mode);

PVOID volatile g_original_shade_model = nullptr;
PVOID volatile g_original_begin = nullptr;
PVOID volatile g_original_draw_arrays = nullptr;
PVOID volatile g_original_draw_elements = nullptr;
PVOID volatile g_polygon_mode = nullptr;
std::uint32_t* g_shade_model_slot = nullptr;
std::uint32_t* g_begin_slot = nullptr;
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

void ForceRendererDiagnostic() noexcept {
    const auto polygon_mode = LoadFunction<GlPolygonMode>(&g_polygon_mode);
    if (polygon_mode != nullptr) {
        polygon_mode(kGlFrontAndBack, kGlLine);
    }
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
    ForceRendererDiagnostic();
    const auto original = LoadFunction<GlBegin>(&g_original_begin);
    if (original != nullptr) {
        original(mode);
    }
}

void APIENTRY StrongDrawArrays(
    const unsigned int mode,
    const int first,
    const int count
) noexcept {
    ForceRendererDiagnostic();
    const auto original = LoadFunction<GlDrawArrays>(&g_original_draw_arrays);
    if (original != nullptr) {
        original(mode, first, count);
    }
}

void APIENTRY StrongDrawElements(
    const unsigned int mode,
    const int count,
    const unsigned int type,
    const void* const indices
) noexcept {
    ForceRendererDiagnostic();
    const auto original = LoadFunction<GlDrawElements>(&g_original_draw_elements);
    if (original != nullptr) {
        original(mode, count, type, indices);
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

DWORD StartStrongCelShading() noexcept {
    static_assert(sizeof(void*) == sizeof(std::uint32_t));
    if (
        g_shade_model_slot != nullptr
        || g_begin_slot != nullptr
        || g_draw_arrays_slot != nullptr
        || g_draw_elements_slot != nullptr
        || g_original_shade_model != nullptr
        || g_original_begin != nullptr
        || g_original_draw_arrays != nullptr
        || g_original_draw_elements != nullptr
        || g_polygon_mode != nullptr
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
    std::array<ImportHookPlan, 4U> plans{{
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
    auto* const image = reinterpret_cast<std::uint8_t*>(executable);
    for (ImportHookPlan& plan : plans) {
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
    for (std::size_t left = 0U; left < plans.size(); ++left) {
        for (std::size_t right = left + 1U; right < plans.size(); ++right) {
            if (plans[left].slot == plans[right].slot) {
                return ERROR_INVALID_DATA;
            }
        }
    }
    PVOID const polygon_mode = reinterpret_cast<PVOID>(GetProcAddress(opengl, "glPolygonMode"));
    if (polygon_mode == nullptr) {
        return ERROR_PROC_NOT_FOUND;
    }
    InterlockedExchangePointer(&g_polygon_mode, polygon_mode);
    for (ImportHookPlan& plan : plans) {
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
        InterlockedExchangePointer(&g_polygon_mode, nullptr);
    }
}

}  // namespace wonderbane::extension
