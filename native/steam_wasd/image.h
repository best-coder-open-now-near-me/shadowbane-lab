#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <array>
#include <fstream>
#include <filesystem>
#include <string>
#include <vector>
#include "profile.h"
namespace steam_wasd {
inline std::vector<unsigned char> read_file(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) return {};
    const auto n = stream.tellg();
    if (n <= 0 || n > 128*1024*1024) return {};
    std::vector<unsigned char> bytes(static_cast<size_t>(n));
    stream.seekg(0); stream.read(reinterpret_cast<char*>(bytes.data()), n);
    return stream ? bytes : std::vector<unsigned char>{};
}
inline std::string hash(const std::vector<unsigned char>& bytes) {
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE context{};
    DWORD size{}, copied{};
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) return {};
    if (BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&size), sizeof(size), &copied, 0) < 0) {
        BCryptCloseAlgorithmProvider(algorithm, 0); return {};
    }
    std::vector<unsigned char> object(size); std::array<unsigned char, 32> digest{};
    bool ok = BCryptCreateHash(algorithm, &context, object.data(), size, nullptr, 0, 0) >= 0;
    if (ok) ok = BCryptHashData(context, const_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()), 0) >= 0
        && BCryptFinishHash(context, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    if (context) BCryptDestroyHash(context);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (!ok) return {};
    std::string out; for (auto c : digest) { out += "0123456789abcdef"[c >> 4]; out += "0123456789abcdef"[c & 15]; }
    return out;
}
inline bool verified_file(const std::vector<unsigned char>& file) { return hash(file) == profile::sha256; }
// Only parse headers after the complete file digest matches the reviewed image.
inline bool verified_loaded_image(std::uintptr_t base) {
    wchar_t path[32768]{};
    if (!GetModuleFileNameW(reinterpret_cast<HMODULE>(base), path, 32768)) return false;
    const auto bytes = read_file(path);
    if (!verified_file(bytes)) return false;
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(bytes.data());
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(bytes.data() + dos->e_lfanew);
    if (nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64) return false;
    const auto* sections = IMAGE_FIRST_SECTION(nt);
    bool checked = false;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; ++i) {
        const auto& s = sections[i];
        if (!(s.Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        if (std::memcmp(reinterpret_cast<void*>(base + s.VirtualAddress), bytes.data() + s.PointerToRawData,
                        s.SizeOfRawData) != 0) return false;
        checked = true;
    }
    return checked && *reinterpret_cast<std::uintptr_t*>(base + profile::update_slot) == base + profile::update;
}
}
