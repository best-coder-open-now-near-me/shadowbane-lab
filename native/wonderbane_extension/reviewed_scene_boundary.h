#pragma once

#include <Windows.h>
#include <bcrypt.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {

// Reviewed 55fbad5f / graphics bootstrap a9a59004 ArcWindowGame::Display.
// See docs/investigations/renderer-scene-boundary.md. No pattern scanning or
// guessed-offset fallback: relocated code must reproduce the entire digest.
constexpr std::uint32_t kSceneDisplayRva = 0x797AD0U;
constexpr std::size_t kSceneDisplaySize = 2421U;
constexpr std::uint32_t kScenePreferredBase = 0x400000U;
constexpr std::uint32_t kSceneClearReturnRva = 0x79810FU;
constexpr std::uint32_t kSceneUiReturnRva = 0x7981FBU;
constexpr std::uint32_t kSceneClearIatRva = 0x16B0990U;
constexpr std::uint32_t kSceneMatrixModeIatRva = 0x16B08ECU;
constexpr std::array<std::size_t, 90U> kSceneDisplayRelocations{
    0x6U, 0x22U, 0x5dU, 0x63U, 0x69U, 0x7bU, 0x8cU, 0xa1U, 0xb3U,
    0xc0U, 0xc9U, 0xebU, 0x110U, 0x175U, 0x185U, 0x19cU, 0x1aaU,
    0x1b3U, 0x235U, 0x23eU, 0x253U, 0x25cU, 0x28bU, 0x2cdU,
    0x2dcU, 0x2f8U, 0x301U, 0x31cU, 0x326U, 0x336U, 0x33cU,
    0x343U, 0x365U, 0x39dU, 0x3b4U, 0x3b9U, 0x3bfU, 0x3cbU,
    0x3eeU, 0x401U, 0x445U, 0x45bU, 0x46aU, 0x477U, 0x4a7U,
    0x4f4U, 0x503U, 0x533U, 0x5c4U, 0x620U, 0x626U, 0x63bU,
    0x640U, 0x64bU, 0x672U, 0x6baU, 0x6c9U, 0x6d3U, 0x6f3U,
    0x6fdU, 0x708U, 0x720U, 0x72dU, 0x735U, 0x73dU, 0x75bU,
    0x76bU, 0x77cU, 0x78cU, 0x792U, 0x797U, 0x7a7U, 0x7c6U,
    0x7d4U, 0x7e1U, 0x829U, 0x834U, 0x839U, 0x83fU, 0x85cU,
    0x866U, 0x879U, 0x88fU, 0x89fU, 0x8b1U, 0x8e4U, 0x924U,
    0x935U, 0x944U, 0x94fU,
};

constexpr std::array<const char*, 4U> kReviewedSceneExecutableHashes{
    "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
    "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8",
    "feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff",
    "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87",
};

inline bool IsReviewedSceneExecutable(const char* const sha256) noexcept {
    if (sha256 == nullptr) { return false; }
    for (const char* reviewed : kReviewedSceneExecutableHashes) {
        if (std::strcmp(sha256, reviewed) == 0) { return true; }
    }
    return false;
}

inline bool IsReviewedSceneDisplayCode(
    const std::uint8_t* const code,
    const std::size_t size,
    const std::uint32_t loaded_base
) noexcept {
    if (code == nullptr || size != kSceneDisplaySize || loaded_base == 0U) {
        return false;
    }
    std::array<std::uint8_t, kSceneDisplaySize> normalized{};
    std::memcpy(normalized.data(), code, size);
    const std::uint32_t delta = loaded_base - kScenePreferredBase;
    for (const std::size_t offset : kSceneDisplayRelocations) {
        std::uint32_t value = 0U;
        std::memcpy(&value, normalized.data() + offset, sizeof(value));
        value -= delta;
        std::memcpy(normalized.data() + offset, &value, sizeof(value));
    }
    constexpr std::array<std::uint8_t, 32U> expected{
        0x77,0x9b,0x83,0xea,0x15,0xec,0x68,0x92,0xa3,0x32,0xfc,0x2d,0x9c,0xc8,0x30,0x8e,
        0x4c,0x54,0x89,0x18,0xcb,0xa8,0x09,0x10,0x57,0xee,0x04,0x90,0x99,0xdd,0x5b,0xe4,
    };
    std::array<std::uint8_t, 32U> digest{};
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    bool valid = false;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM,
            nullptr, 0U) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0U, nullptr, 0U, 0U) >= 0
        && BCryptHashData(hash, normalized.data(),
            static_cast<ULONG>(normalized.size()), 0U) >= 0
        && BCryptFinishHash(hash, digest.data(),
            static_cast<ULONG>(digest.size()), 0U) >= 0) {
        valid = digest == expected;
    }
    if (hash != nullptr) { BCryptDestroyHash(hash); }
    if (algorithm != nullptr) { BCryptCloseAlgorithmProvider(algorithm, 0U); }
    return valid;
}

inline bool IsReviewedSceneCall(
    const std::uintptr_t return_address,
    const std::uintptr_t image_base,
    const std::uint32_t return_rva
) noexcept {
    return image_base != 0U && return_address >= image_base
        && return_address - image_base == return_rva;
}

}  // namespace wonderbane::extension
