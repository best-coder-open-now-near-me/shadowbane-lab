#include "cel_shading.h"
#include "import_hook.h"

#include <Windows.h>

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {

constexpr std::size_t kImageSize = 0x800U;
constexpr std::uint32_t kNtRva = 0x80U;
constexpr std::uint32_t kImportRva = 0x200U;
constexpr std::uint32_t kLibraryRva = 0x300U;
constexpr std::uint32_t kNamesRva = 0x340U;
constexpr std::uint32_t kAddressesRva = 0x380U;
constexpr std::array<std::uint32_t, 5U> kImportNameRvas{
    0x3C0U,
    0x3E0U,
    0x400U,
    0x420U,
    0x440U,
};
constexpr std::array<const char*, 5U> kImportNames{
    "glShadeModel",
    "glBegin",
    "glCallList",
    "glDrawArrays",
    "glDrawElements",
};
constexpr std::array<std::uint32_t, 5U> kImportAddresses{
    0x12345678U,
    0x23456789U,
    0x3456789AU,
    0x456789ABU,
    0x56789ABCU,
};

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

void WriteImport(
    std::vector<std::uint8_t>& image,
    const std::size_t index,
    const std::uint32_t name_rva,
    const char* const name,
    const std::uint32_t address
) {
    auto* const names = reinterpret_cast<IMAGE_THUNK_DATA32*>(image.data() + kNamesRva);
    auto* const addresses = reinterpret_cast<IMAGE_THUNK_DATA32*>(
        image.data() + kAddressesRva
    );
    names[index].u1.AddressOfData = name_rva;
    addresses[index].u1.Function = address;
    auto* const import_name = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(image.data() + name_rva);
    import_name->Hint = static_cast<WORD>(index);
    std::memcpy(import_name->Name, name, std::strlen(name) + 1U);
}

std::vector<std::uint8_t> Fixture() {
    std::vector<std::uint8_t> image(kImageSize);
    auto* const dos = reinterpret_cast<IMAGE_DOS_HEADER*>(image.data());
    dos->e_magic = IMAGE_DOS_SIGNATURE;
    dos->e_lfanew = kNtRva;
    auto* const nt = reinterpret_cast<IMAGE_NT_HEADERS32*>(image.data() + kNtRva);
    nt->Signature = IMAGE_NT_SIGNATURE;
    nt->FileHeader.Machine = IMAGE_FILE_MACHINE_I386;
    nt->OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR32_MAGIC;
    nt->OptionalHeader.SizeOfImage = static_cast<std::uint32_t>(image.size());
    nt->OptionalHeader.NumberOfRvaAndSizes = IMAGE_NUMBEROF_DIRECTORY_ENTRIES;
    nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT] = {
        kImportRva,
        2U * sizeof(IMAGE_IMPORT_DESCRIPTOR),
    };
    auto* const imports = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(
        image.data() + kImportRva
    );
    imports[0].Name = kLibraryRva;
    imports[0].OriginalFirstThunk = kNamesRva;
    imports[0].FirstThunk = kAddressesRva;
    std::memcpy(image.data() + kLibraryRva, "OPENGL32.dll", 13U);
    for (std::size_t index = 0U; index < kImportNames.size(); ++index) {
        WriteImport(
            image,
            index,
            kImportNameRvas[index],
            kImportNames[index],
            kImportAddresses[index]
        );
    }
    return image;
}

}  // namespace

int wmain() {
    std::vector<std::uint8_t> image = Fixture();
    for (std::size_t index = 0U; index < kImportNames.size(); ++index) {
        std::uint32_t* const slot = wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "opengl32.DLL",
            kImportNames[index]
        );
        if (slot == nullptr || *slot != kImportAddresses[index]) {
            return Fail(L"exact import resolution");
        }
    }
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glColor4f"
        ) != nullptr) {
        return Fail(L"missing symbol rejection");
    }
    auto* const names = reinterpret_cast<IMAGE_THUNK_DATA32*>(image.data() + kNamesRva);
    auto* const addresses = reinterpret_cast<IMAGE_THUNK_DATA32*>(
        image.data() + kAddressesRva
    );
    names[5].u1.AddressOfData = kImportNameRvas[0];
    addresses[5].u1.Function = 0x6789ABCDU;
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glShadeModel"
        ) != nullptr) {
        return Fail(L"duplicate symbol rejection");
    }
    image = Fixture();
    auto* const nt = reinterpret_cast<IMAGE_NT_HEADERS32*>(image.data() + kNtRva);
    nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].Size = (
        sizeof(IMAGE_IMPORT_DESCRIPTOR)
    );
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glShadeModel"
        ) != nullptr) {
        return Fail(L"unterminated descriptor rejection");
    }
    image = Fixture();
    auto* const imports = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(
        image.data() + kImportRva
    );
    imports[0].FirstThunk = static_cast<std::uint32_t>(image.size());
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glShadeModel"
        ) != nullptr) {
        return Fail(L"out-of-range thunk rejection");
    }

    constexpr std::array<float, 16U> perspective{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, -1.0F, -1.0F,
        0.0F, 0.0F, -0.2F, 0.0F,
    };
    constexpr std::array<float, 16U> orthographic{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, -1.0F, 0.0F,
        0.0F, 0.0F, 0.0F, 1.0F,
    };
    if (!wonderbane::extension::IsPerspectiveProjectionMatrix(
            perspective.data(),
            perspective.size()
        )) {
        return Fail(L"perspective projection acceptance");
    }
    if (wonderbane::extension::IsPerspectiveProjectionMatrix(
            orthographic.data(),
            orthographic.size()
        )) {
        return Fail(L"orthographic projection rejection");
    }
    if (
        !wonderbane::extension::IsOutlinePrimitive(0x0004U, 36)
        || wonderbane::extension::IsOutlinePrimitive(0x0001U, 36)
        || wonderbane::extension::IsOutlinePrimitive(0x0004U, 8193)
    ) {
        return Fail(L"bounded outline primitive policy");
    }
    if (
        wonderbane::extension::CelShadingHookCount(
            wonderbane::extension::CelShadingProfile::native
        ) != 0U
        || wonderbane::extension::CelShadingHookCount(
            wonderbane::extension::CelShadingProfile::flat
        ) != 1U
        || wonderbane::extension::CelShadingHookCount(
            wonderbane::extension::CelShadingProfile::outlined
        ) != 5U
    ) {
        return Fail(L"cel profile hook counts");
    }
    wonderbane::extension::CelShadingProfile profile{};
    if (
        wonderbane::extension::SelectCelShadingProfile(nullptr, &profile) != ERROR_SUCCESS
        || profile != wonderbane::extension::CelShadingProfile::native
        || wonderbane::extension::SelectCelShadingProfile(L"native", &profile) != ERROR_SUCCESS
        || profile != wonderbane::extension::CelShadingProfile::native
        || wonderbane::extension::SelectCelShadingProfile(L"flat", &profile) != ERROR_SUCCESS
        || profile != wonderbane::extension::CelShadingProfile::flat
        || wonderbane::extension::SelectCelShadingProfile(L"outlined", &profile)
            != ERROR_SUCCESS
        || profile != wonderbane::extension::CelShadingProfile::outlined
        || wonderbane::extension::SelectCelShadingProfile(L"OUTLINED", &profile)
            != ERROR_INVALID_DATA
        || wonderbane::extension::SelectCelShadingProfile(L"outlined", nullptr)
            != ERROR_INVALID_PARAMETER
    ) {
        return Fail(L"cel profile policy");
    }
    return 0;
}
