#include "cel_shading.h"

#include <Windows.h>

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
constexpr std::uint32_t kImportNameRva = 0x3C0U;

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
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
    auto* const names = reinterpret_cast<IMAGE_THUNK_DATA32*>(image.data() + kNamesRva);
    names[0].u1.AddressOfData = kImportNameRva;
    auto* const addresses = reinterpret_cast<IMAGE_THUNK_DATA32*>(
        image.data() + kAddressesRva
    );
    addresses[0].u1.Function = 0x12345678U;
    auto* const import_name = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(
        image.data() + kImportNameRva
    );
    import_name->Hint = 7U;
    std::memcpy(import_name->Name, "glShadeModel", 13U);
    return image;
}

}  // namespace

int wmain() {
    std::vector<std::uint8_t> image = Fixture();
    std::uint32_t* const slot = wonderbane::extension::FindImportAddressSlot(
        image.data(),
        image.size(),
        "opengl32.DLL",
        "glShadeModel"
    );
    if (slot == nullptr || *slot != 0x12345678U) {
        return Fail(L"exact import resolution");
    }
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glDrawElements"
        ) != nullptr) {
        return Fail(L"missing symbol rejection");
    }
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
    return 0;
}
