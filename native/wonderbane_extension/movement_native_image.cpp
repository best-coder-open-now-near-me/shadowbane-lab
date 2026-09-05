#include "movement_native_image.h"
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <vector>
namespace wonderbane::extension::movement {
namespace {
bool ReadLoaded(void* output, const void* input, std::size_t size) noexcept {
    __try { std::memcpy(output, input, size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool ReviewedDigest(const std::vector<unsigned char>& bytes) noexcept {
    constexpr std::array<unsigned char, 32> expected{
        0xfe,0xb3,0x51,0xf0,0xfa,0xe8,0x7d,0x47,0x54,0x9f,0xa4,0x3c,0x37,0x83,0x64,0x05,
        0xa7,0x53,0xd7,0x6f,0xbc,0xd0,0xb0,0x22,0x32,0xfc,0x1c,0x07,0x33,0x55,0x0d,0xff};
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE hash{};
    std::array<unsigned char, 32> digest{};
    const bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, const_cast<unsigned char*>(bytes.data()), static_cast<ULONG>(bytes.size()), 0) >= 0
        && BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); }
    if (algorithm) { BCryptCloseAlgorithmProvider(algorithm, 0); }
    return ok && digest == expected;
}
template<class T> bool FileValue(const std::vector<unsigned char>& bytes, std::size_t offset, T& output) {
    if (offset > bytes.size() || sizeof(T) > bytes.size() - offset) { return false; }
    std::memcpy(&output, bytes.data() + offset, sizeof(T)); return true;
}
bool Verify(std::uintptr_t& output) {
    std::array<wchar_t, 32768> path{};
    const auto path_size = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    if (!path_size || path_size >= path.size()) { return false; }
    std::ifstream file(std::filesystem::path(path.data()), std::ios::binary | std::ios::ate);
    if (!file) { return false; }
    const auto size = file.tellg();
    if (size <= 0 || size > 64 * 1024 * 1024) { return false; }
    std::vector<unsigned char> bytes(static_cast<std::size_t>(size));
    file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(bytes.data()), size) || !ReviewedDigest(bytes)) { return false; }
    IMAGE_DOS_HEADER dos{}; IMAGE_NT_HEADERS32 nt{};
    if (!FileValue(bytes, 0, dos) || dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < 0
        || !FileValue(bytes, static_cast<std::size_t>(dos.e_lfanew), nt)
        || nt.Signature != IMAGE_NT_SIGNATURE || nt.OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
        || nt.OptionalHeader.ImageBase != 0x400000 || nt.FileHeader.NumberOfSections > 96) { return false; }
    IMAGE_SECTION_HEADER text{}, reloc{};
    const std::size_t first = static_cast<std::size_t>(dos.e_lfanew) + 24 + nt.FileHeader.SizeOfOptionalHeader;
    for (std::size_t i = 0; i < nt.FileHeader.NumberOfSections; ++i) {
        IMAGE_SECTION_HEADER section{};
        if (!FileValue(bytes, first + i * sizeof(section), section)) { return false; }
        if (std::memcmp(section.Name, ".text", 6) == 0) { text = section; }
        if (std::memcmp(section.Name, ".reloc", 7) == 0) { reloc = section; }
    }
    if (text.VirtualAddress != 0x1000 || text.PointerToRawData != 0x1000 || text.SizeOfRawData != 0x1140000
        || text.PointerToRawData + text.SizeOfRawData > bytes.size()) { return false; }
    const auto base = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    std::vector<unsigned char> loaded(text.SizeOfRawData);
    if (!base || !ReadLoaded(loaded.data(), reinterpret_cast<const void*>(base + text.VirtualAddress), loaded.size())) {
        return false;
    }
    const auto directory = nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if (directory.VirtualAddress < reloc.VirtualAddress || directory.Size > reloc.SizeOfRawData
        || directory.VirtualAddress - reloc.VirtualAddress > reloc.SizeOfRawData - directory.Size) { return false; }
    std::size_t cursor = reloc.PointerToRawData + directory.VirtualAddress - reloc.VirtualAddress;
    const std::size_t end = cursor + directory.Size;
    if (end > bytes.size()) { return false; }
    const auto delta = static_cast<std::uint32_t>(base - 0x400000U);
    while (cursor < end) {
        IMAGE_BASE_RELOCATION block{};
        if (!FileValue(bytes, cursor, block) || block.SizeOfBlock < 8 || block.SizeOfBlock > end - cursor
            || block.SizeOfBlock % 2 != 0) { return false; }
        for (std::size_t at = cursor + 8; at < cursor + block.SizeOfBlock; at += 2) {
            std::uint16_t entry{};
            if (!FileValue(bytes, at, entry)) { return false; }
            const auto rva = block.VirtualAddress + (entry & 0xfffU);
            if ((entry >> 12) == IMAGE_REL_BASED_HIGHLOW && rva >= text.VirtualAddress
                && rva - text.VirtualAddress <= loaded.size() - 4) {
                std::uint32_t value{};
                std::memcpy(&value, loaded.data() + rva - text.VirtualAddress, 4);
                value -= delta;
                std::memcpy(loaded.data() + rva - text.VirtualAddress, &value, 4);
            }
        }
        cursor += block.SizeOfBlock;
    }
    if (std::memcmp(loaded.data(), bytes.data() + text.PointerToRawData, loaded.size()) != 0) { return false; }
    output = base; return true;
}
}
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept {
    base = 0;
    try { return Verify(base); } catch (...) { return false; }
}
}
